"""An unchecked large document must not reach the customer.

A six-page invoice that does not add up gets eyeballed by whoever opens it. A
656-page one does not, so shipping it unverified is worse than shipping nothing.
The completed/ package is written either way; this gates only the copy into the
supplier's delivery folder.
"""

from decimal import Decimal

import pytest

from polaris.config import settings
from polaris.pipeline.processor import _unverified_large_document_blockers
from polaris.validation.schema import (
    ExtractedDocument,
    ExtractionMetadata,
    ExtractionPath,
    ReconciliationResult,
)


def _invoice(pages: int) -> ExtractedDocument:
    return ExtractedDocument(
        intake_id="t",
        metadata=ExtractionMetadata(extraction_path=ExtractionPath.AI, total_pages=pages),
    )


def _recon(*, reconciled: bool) -> ReconciliationResult:
    return ReconciliationResult(
        line_items_sum=Decimal("100.00"),
        computed_total=Decimal("100.00"),
        variance=Decimal("0.00") if reconciled else Decimal("180.76"),
        variance_pct=0.0 if reconciled else 0.064,
        is_reconciled=reconciled,
        verification_status="reconciled" if reconciled else "mismatch",
    )


@pytest.fixture(autouse=True)
def _threshold(monkeypatch):
    monkeypatch.setattr(settings, "blocking_check_page_threshold", 100)


def test_a_large_document_that_fails_its_check_is_held_back():
    blockers = _unverified_large_document_blockers(_invoice(656), _recon(reconciled=False))
    assert len(blockers) == 1
    assert "656-page" in blockers[0]
    assert "6.40%" in blockers[0]


def test_a_large_document_that_reconciles_is_delivered():
    assert _unverified_large_document_blockers(_invoice(656), _recon(reconciled=True)) == []


def test_a_small_document_is_delivered_even_when_it_fails():
    """Short enough to check by hand — the warning is the right response, not a block."""
    assert _unverified_large_document_blockers(_invoice(8), _recon(reconciled=False)) == []


def test_the_threshold_is_inclusive_at_its_boundary():
    assert _unverified_large_document_blockers(_invoice(99), _recon(reconciled=False)) == []
    assert _unverified_large_document_blockers(_invoice(100), _recon(reconciled=False)) != []


def test_an_unverifiable_document_is_not_blocked():
    """No reconcilable totals is the normal state for a document with no arithmetic.

    Blocking it would make the gate unusable the moment Polaris handles
    something other than invoices.
    """
    assert _unverified_large_document_blockers(_invoice(656), None) == []


def test_zero_disables_the_gate(monkeypatch):
    monkeypatch.setattr(settings, "blocking_check_page_threshold", 0)
    assert _unverified_large_document_blockers(_invoice(656), _recon(reconciled=False)) == []


# ---------------------------------------------------------------------------
# A profile with nothing configured to deliver stops before any AI is spent;
# an invoice with no profile at all ships the raw extraction workbook.
# ---------------------------------------------------------------------------


def _profile(**kw):
    from polaris.profiles.schema import SupplierIdentity, SupplierProfile

    base = dict(profile_id="acme.v1", identity=SupplierIdentity(canonical_name="Acme"))
    base.update(kw)
    return SupplierProfile(**base)


def test_a_profile_with_no_columns_is_a_configuration_blocker():
    from polaris.output.columns import OutputColumn
    from polaris.pipeline.processor import _profile_configuration_blockers

    assert _profile_configuration_blockers(None) == []
    assert _profile_configuration_blockers(_profile()) == ["no output columns configured"]
    ready = _profile(output_columns=[OutputColumn(header="A", source="row.amount")])
    assert _profile_configuration_blockers(ready) == []


def test_the_configuration_gate_parks_the_invoice_and_does_not_retry(tmp_path, monkeypatch):
    from polaris.pipeline.processor import NonRetryablePipelineError, _stop_if_profile_cannot_deliver

    monkeypatch.setattr(settings, "exceptions_dir", tmp_path / "exceptions")
    logged = []

    class _Db:
        pass

    monkeypatch.setattr(
        "polaris.pipeline.processor.crud.log_processing_step",
        lambda db, **kw: logged.append(kw),
    )
    with pytest.raises(NonRetryablePipelineError, match="no output columns configured"):
        _stop_if_profile_cannot_deliver(_Db(), "intake-1", tmp_path / "missing.pdf", _profile())
    assert (tmp_path / "exceptions" / "intake-1" / "error_log.json").exists()
    assert logged and logged[0]["step"] == "configuration"


def test_no_profile_invoice_gets_the_raw_workbook(tmp_path):
    import openpyxl

    from polaris.output.xlsx_writer import write_raw_workbook

    invoice = ExtractedDocument(
        intake_id="t",
        fields={"supplier_name": "Acme", "invoice_number": "INV-1", "invoice_date": "2026-01-02",
                "total_due": Decimal("10.50"), "cost_centre": "CC-9"},
        rows=[{"line_number": 1, "description": "svc", "amount": Decimal("10.50"), "charge_type": "recurring",
               "service_id": "S1", "site_code": "lhr"}],
        metadata=ExtractionMetadata(extraction_path=ExtractionPath.AI),
    )
    path = write_raw_workbook(invoice, tmp_path / "raw.xlsx")
    wb = openpyxl.load_workbook(path)
    assert wb.sheetnames == ["Invoice", "Line items"]
    invoice_sheet = {row[0]: row[1] for row in wb["Invoice"].iter_rows(min_row=2, values_only=True)}
    assert invoice_sheet["invoice_number"] == "INV-1"
    assert invoice_sheet["total_due"] == 10.5
    assert invoice_sheet["cost_centre"] == "CC-9"
    items = list(wb["Line items"].iter_rows(values_only=True))
    assert items[0][:3] == ("service_id", "description", "charge_type")
    assert "site_code" in items[0]
    assert items[1][items[0].index("amount")] == 10.5


def test_a_large_failed_document_with_no_profile_is_parked_not_crashed(tmp_path, monkeypatch):
    """Regression: the gate read profile.profile_id with no profile, so a 100+
    page AI-only invoice that did not reconcile crashed after extraction and the
    task retry re-ran the whole (paid) extraction."""
    import json

    from polaris.pipeline.processor import _pause_delivery

    monkeypatch.setattr(settings, "exceptions_dir", tmp_path / "exceptions")
    monkeypatch.setattr(settings, "blocking_check_page_threshold", 100)
    invoice = _invoice(656)
    blockers = _unverified_large_document_blockers(invoice, _recon(reconciled=False))

    _pause_delivery("intake-2", tmp_path / "missing.pdf", invoice, None, blockers)

    log = json.loads((tmp_path / "exceptions" / "intake-2" / "error_log.json").read_text(encoding="utf-8"))
    assert "656-page document failed its arithmetic check" in json.dumps(log)
