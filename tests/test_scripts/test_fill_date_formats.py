"""scripts/fill_date_formats.py against the corpus invoices in an isolated DB.

Profiles migrated from the shared registries deliver dates without a printed
format. The script reads the dates off each profile's archived invoices and
writes only the formats exactly one strptime pattern fits: Colt prints
``01-Feb-2024`` (one reading), euNetworks ``02/12/2025`` (two), so the first
is filled and the second is reported for a human to resolve with ``--set``.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import sys
from pathlib import Path

import pytest

from polaris.config import settings
from polaris.db import crud
from polaris.db import session as db_session
from polaris.db.models import AuditEvent, IntakeRecord
from polaris.fields.schema import FieldDef, FieldScope
from polaris.models import registry
from polaris.models.schema import ExtractionModel
from polaris.output.columns import OutputColumn
from polaris.profiles.contract import date_format_issues, field_set, output_columns
from polaris.profiles.loader import get_profile, save_profile
from polaris.profiles.schema import SupplierProfile
from tests.corpus_utils import CORPUS_ROOT

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "fill_date_formats.py"
COLT = "colt.standard.v1"
EUNETWORKS = "eunetworks.standard.v2"
COLT_PDFS = [CORPUS_ROOT / "colt.standard" / "invoices" / name
             for name in ("676198608_20240201.pdf", "684231629_20240401.pdf")]
EUNETWORKS_PDFS = [CORPUS_ROOT / "eunetworks.standard" / "invoices" / name
                   for name in ("A837737 - IE-SI53564.pdf", "A837737 - IE-SI53566.pdf")]
COLT_MODEL = "colt.standard.v1"
COLT_FINGERPRINT = "fp-colt-unchanged"


def _load_script():
    spec = importlib.util.spec_from_file_location("fill_date_formats", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Dataclasses with postponed annotations resolve them through sys.modules.
    sys.modules["fill_date_formats"] = module
    spec.loader.exec_module(module)
    return module


def _without_formats(profile: SupplierProfile) -> SupplierProfile:
    for entry in profile.fields:
        if entry.type == "date":
            entry.date_format = None
    return profile


def _archive(db, tmp_path: Path, profile_id: str, pdfs: list[Path]) -> list[str]:
    ids = []
    for index, pdf in enumerate(pdfs):
        intake_id = f"intake-{profile_id}-{index}"
        target = tmp_path / "archive" / intake_id / "original.pdf"
        target.parent.mkdir(parents=True)
        shutil.copyfile(pdf, target)
        db.add(IntakeRecord(
            id=intake_id, original_filename=pdf.name, original_pdf_path=str(pdf),
            supplier_profile_id=profile_id, status="completed",
        ))
        ids.append(intake_id)
    db.commit()
    return ids


@pytest.fixture()
def script(isolated_db):
    return _load_script()


@pytest.fixture()
def seeded(isolated_db, tmp_path, monkeypatch, corpus_profile) -> dict[str, SupplierProfile]:
    """Colt and euNetworks corpus profiles with every date format nulled, two
    archived completed invoices each, and one approved Colt model authored on
    the first Colt invoice."""
    monkeypatch.setattr(settings, "archive_dir", tmp_path / "archive")
    monkeypatch.setattr(settings, "extraction_models_dir", tmp_path / "models")
    colt = _without_formats(corpus_profile("colt.standard"))
    next(f for f in colt.fields if f.name == "due_date").label_hint = "Due Date"
    eunetworks = _without_formats(corpus_profile("eunetworks.standard"))
    assert eunetworks.profile_id == EUNETWORKS
    save_profile(colt)
    save_profile(eunetworks)

    db = db_session.SessionLocal()
    colt_intakes = _archive(db, tmp_path, COLT, COLT_PDFS)
    _archive(db, tmp_path, EUNETWORKS, EUNETWORKS_PDFS)
    registry.save_model(db, ExtractionModel(
        model_id=COLT_MODEL, supplier_profile_id=COLT, supplier="Colt",
        layout_fingerprint=COLT_FINGERPRINT, created_from_intake=colt_intakes[0],
    ))
    crud.update_model_status(db, COLT_MODEL, "approved", approved_by="tests")
    db.close()
    return {COLT: colt, EUNETWORKS: eunetworks}


def _events(action: str) -> list[AuditEvent]:
    db = db_session.SessionLocal()
    try:
        return db.query(AuditEvent).filter_by(entity_type="profile", action=action).all()
    finally:
        db.close()


def _formats(profile_id: str) -> dict[str, str | None]:
    profile = get_profile(profile_id)
    return {f.name: f.date_format for f in profile.fields if f.type == "date"}


def _issue_paths(profile: SupplierProfile) -> set[str]:
    issues = date_format_issues(output_columns(profile), field_set(profile))
    return {re.search(r"'([^']+)'", issue).group(1) for issue in issues}


# ---------------------------------------------------------------------------
# Dry run and apply
# ---------------------------------------------------------------------------


def test_dry_run_reports_colt_without_writing(seeded, script, capsys):
    assert script.main([]) == 0

    out = capsys.readouterr().out
    line = next(line for line in out.splitlines() if "field.invoice_date" in line and COLT not in line)
    assert "%d-%b-%Y" in line and "would set" in line
    assert "Re-run with --apply to write." in out
    assert _formats(COLT) == {"invoice_date": None, "due_date": None}


def test_apply_writes_colt_formats_and_audits(seeded, script):
    assert script.main(["--apply", "--profile", COLT]) == 0

    assert _formats(COLT) == {"invoice_date": "%d-%b-%Y", "due_date": "%d-%b-%Y"}
    colt = get_profile(COLT)
    assert date_format_issues(output_columns(colt), field_set(colt)) == []
    (event,) = _events("date_formats_filled")
    assert event.entity_id == COLT
    assert event.event_metadata["formats"] == {"field.invoice_date": "%d-%b-%Y", "field.due_date": "%d-%b-%Y"}
    assert event.event_metadata["by"] == "fill_date_formats.py"
    assert event.event_metadata["source_intakes"][0] == f"intake-{COLT}-0"  # the model's authoring invoice first
    assert event.event_metadata["overrides"] == []
    assert _events("models_rekeyed") == []
    db = db_session.SessionLocal()
    try:
        assert crud.get_extraction_model(db, COLT_MODEL).layout_fingerprint == COLT_FINGERPRINT
    finally:
        db.close()


def test_eunetworks_slash_dates_are_ambiguous_and_not_written(seeded, script, capsys):
    assert script.main(["--apply", "--profile", EUNETWORKS]) == 0

    out = capsys.readouterr().out
    line = next(line for line in out.splitlines() if "field.invoice_date" in line and EUNETWORKS not in line)
    assert "ambiguous" in line
    assert "%d/%m/%Y" in out and "%m/%d/%Y" in out
    assert "2025-12-02" in out and "2025-02-12" in out  # both readings of 02/12/2025
    assert f"--set {EUNETWORKS}:field.invoice_date=" in out
    assert _formats(EUNETWORKS) == {"invoice_date": None, "due_date": None}
    assert _events("date_formats_filled") == []


def test_set_override_writes_the_chosen_format(seeded, script):
    assert script.main(["--set", f"{EUNETWORKS}:field.invoice_date=%d/%m/%Y", "--apply", "--profile", EUNETWORKS]) == 0

    assert _formats(EUNETWORKS) == {"invoice_date": "%d/%m/%Y", "due_date": None}
    (event,) = _events("date_formats_filled")
    assert event.event_metadata["formats"] == {"field.invoice_date": "%d/%m/%Y"}
    assert event.event_metadata["overrides"] == ["field.invoice_date"]


def test_bad_set_format_exits_2(seeded, script, capsys):
    assert script.main(["--set", f"{EUNETWORKS}:field.invoice_date=%d/%m/%Q", "--apply"]) == 2
    assert "not a usable strptime format" in capsys.readouterr().err


def test_set_on_a_path_that_is_not_a_gap_exits_2(seeded, script, capsys):
    assert script.main(["--set", f"{EUNETWORKS}:field.account_number=%d/%m/%Y"]) == 2
    assert "field.account_number" in capsys.readouterr().err
    assert script.main(["--set", "nobody.v1:field.invoice_date=%d/%m/%Y"]) == 2
    assert "unknown profile" in capsys.readouterr().err
    assert script.main(["--set", "garbage"]) == 2


def test_unknown_profile_exits_2(seeded, script, capsys):
    assert script.main(["--profile", "nobody.v1"]) == 2
    assert "nobody.v1" in capsys.readouterr().err


def test_profile_without_archived_invoice_is_skipped(seeded, script, capsys, corpus_profile):
    lonely = _without_formats(corpus_profile("colt.standard"))
    lonely.profile_id = "colt.lonely.v1"
    save_profile(lonely)

    assert script.main(["--profile", "colt.lonely.v1"]) == 0

    out = capsys.readouterr().out
    assert "colt.lonely.v1" in out
    assert "skipped: no archived invoice to read" in out
    assert "1 profile(s) skipped" in out
    assert _formats("colt.lonely.v1") == {"invoice_date": None, "due_date": None}


def test_row_billing_period_takes_the_printed_period_format(seeded, script, capsys):
    colt = get_profile(COLT)
    colt.fields.append(FieldDef(name="billing_period_start", scope=FieldScope.ROW))
    colt.output_columns.append(OutputColumn(header="EXT_PERIOD", source="row.billing_period_start"))
    save_profile(colt)

    assert script.main(["--profile", COLT]) == 0

    out = capsys.readouterr().out
    line = next(line for line in out.splitlines() if "row.billing_period_start" in line)
    assert "%d %b %Y" in line and "would set" in line  # Colt prints "01 Feb 2024 - 29 Feb 2024"


def test_missing_label_is_reported_with_the_rows_that_print_dates(seeded, script, capsys):
    colt = get_profile(COLT)
    next(f for f in colt.fields if f.name == "due_date").label_hint = "Payment Due"  # the invoice says "Due Date"
    save_profile(colt)

    assert script.main(["--profile", COLT]) == 0

    out = capsys.readouterr().out
    line = next(line for line in out.splitlines() if "field.due_date" in line)
    assert "not found" in line
    assert "label 'Payment Due' not found" in out
    assert "Due Date 02-Mar-2024" in out


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("samples", "expected"), [
    (["15/04/2024"], ["%d/%m/%Y"]),
    (["03/04/2024"], ["%m/%d/%Y", "%d/%m/%Y"]),
    (["03/04/2024", "15/04/2024"], ["%d/%m/%Y"]),
    (["01 Feb 2024"], ["%d %b %Y"]),
    (["Feb. 1, 2024"], ["%b. %d, %Y"]),
    (["February 2024"], []),
    ([], []),
])
def test_formats_parsing_all(script, samples, expected):
    assert script.formats_parsing_all(samples) == expected


@pytest.mark.parametrize("layout", ["colt.standard", "eunetworks.standard"])
def test_missing_date_paths_agrees_with_the_contract(script, corpus_profile, layout):
    profile = _without_formats(corpus_profile(layout))

    gaps = script.missing_date_paths(profile)

    assert {path for path, _ in gaps} == _issue_paths(profile) == {"field.invoice_date", "field.due_date"}
    assert all(field.type == "date" and field.date_format is None for _, field in gaps)
    for entry in profile.fields:
        if entry.type == "date":
            entry.date_format = "%d/%m/%Y"
    assert script.missing_date_paths(profile) == [] and _issue_paths(profile) == set()


def test_parse_set_args_round_trips_formats(script):
    assert script.parse_set_args([f"{COLT}:field.invoice_date=%d-%b-%Y", f"{COLT}:header.due_date=%d %b %Y"]) == {
        COLT: {"field.invoice_date": "%d-%b-%Y", "field.due_date": "%d %b %Y"},
    }
    with pytest.raises(ValueError):
        script.parse_set_args([f"{COLT}:field.invoice_date=%Q"])
    with pytest.raises(ValueError):
        script.parse_set_args(["field.invoice_date=%d-%b-%Y"])
