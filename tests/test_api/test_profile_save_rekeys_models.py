"""A profile save that changes the fingerprint salt re-keys the profile's templates.

A model is routed by (supplier_profile_id, layout_fingerprint), and the hash is
salted by the profile's fingerprint rules. Before the save path re-keyed, an
edit to those rules silently orphaned every approved model: the pipeline
computed a new hash for the same layout, found no model under it, and sent
every later invoice to AI with a layout-drift exception.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from polaris.db import crud
from polaris.db import session as db_session
from polaris.db.models import AuditEvent, IntakeRecord
from polaris.fingerprint.fingerprinter import fingerprint_pdf
from polaris.main import app
from polaris.models import registry
from polaris.models.schema import ExtractionModel
from polaris.profiles.loader import get_profile, save_profile
from polaris.profiles.schema import SupplierProfile
from tests.corpus_utils import CORPUS_ROOT

LAYOUT = "colt.standard"
PDF = CORPUS_ROOT / LAYOUT / "invoices" / "676198608_20240201.pdf"
INTAKE_ID = "intake-colt-authoring"
MODEL_ID = "colt.standard.v1"
# Drops a label the Colt fingerprint is keyed on, so the recomputed hash differs.
SALT_EDIT = r"(?i)^due date$"


@pytest.fixture()
def seeded(isolated_db, tmp_path, monkeypatch, corpus_profile) -> tuple[SupplierProfile, str]:
    """The corpus Colt profile with one approved model keyed under its current fingerprint."""
    monkeypatch.setattr(registry.settings, "extraction_models_dir", tmp_path / "models")
    monkeypatch.setattr(registry.settings, "archive_dir", tmp_path / "archive")
    profile = corpus_profile(LAYOUT)
    for field in profile.fields:  # the PUT's readiness gate wants a printed format per delivered date
        if field.type == "date":
            field.date_format = "%d %b %Y"
    save_profile(profile)
    fingerprint, _ = fingerprint_pdf(PDF, profile=profile)

    db = db_session.SessionLocal()
    db.add(IntakeRecord(id=INTAKE_ID, original_filename=PDF.name, original_pdf_path=str(PDF), status="completed"))
    db.commit()
    registry.save_model(
        db,
        ExtractionModel(
            model_id=MODEL_ID, supplier_profile_id=profile.profile_id, supplier="Colt",
            layout_fingerprint=fingerprint, created_from_intake=INTAKE_ID,
        ),
    )
    crud.update_model_status(db, MODEL_ID, "approved", approved_by="tests")
    db.close()
    return profile, fingerprint


def _archive_authoring_pdf(tmp_path: Path) -> None:
    target = tmp_path / "archive" / INTAKE_ID / "original.pdf"
    target.parent.mkdir(parents=True)
    shutil.copyfile(PDF, target)


def _put(profile: SupplierProfile):
    return TestClient(app).put(f"/api/v1/profiles/{profile.profile_id}", json=profile.model_dump(mode="json"))


def _stored_fingerprint() -> str:
    db = db_session.SessionLocal()
    try:
        return crud.get_extraction_model(db, MODEL_ID).layout_fingerprint
    finally:
        db.close()


def _rekey_audit_events() -> list[AuditEvent]:
    db = db_session.SessionLocal()
    try:
        return db.query(AuditEvent).filter_by(entity_type="profile", action="models_rekeyed").all()
    finally:
        db.close()


def test_salt_changing_save_rekeys_the_model(seeded, tmp_path):
    profile, old_fingerprint = seeded
    _archive_authoring_pdf(tmp_path)
    edited = profile.model_copy(deep=True)
    edited.layout_fingerprint.ignore_label_patterns.append(SALT_EDIT)

    response = _put(edited)

    assert response.status_code == 200, response.text
    assert response.json()["rekey"] == {"rekeyed": 1, "unchanged": 0, "failed": []}
    expected, _ = fingerprint_pdf(PDF, profile=get_profile(profile.profile_id))
    assert expected != old_fingerprint
    assert _stored_fingerprint() == expected
    (event,) = _rekey_audit_events()
    assert event.entity_id == profile.profile_id
    assert event.event_metadata == {"rekeyed": [MODEL_ID], "unchanged": [], "failed": []}


def test_unrelated_edit_leaves_the_fingerprint_alone(seeded, tmp_path):
    profile, old_fingerprint = seeded
    _archive_authoring_pdf(tmp_path)
    edited = profile.model_copy(deep=True)
    edited.notes = "Ask Colt about the credit note numbering"

    response = _put(edited)

    assert response.status_code == 200, response.text
    assert response.json()["rekey"] is None
    assert _stored_fingerprint() == old_fingerprint
    assert _rekey_audit_events() == []


def test_missing_archive_is_reported_not_raised(seeded):
    profile, old_fingerprint = seeded  # no archived PDF for the authoring intake
    edited = profile.model_copy(deep=True)
    edited.layout_fingerprint.ignore_label_patterns.append(SALT_EDIT)

    with capture_logs() as logs:
        response = _put(edited)

    assert response.status_code == 200, response.text
    assert response.json()["rekey"] == {"rekeyed": 0, "unchanged": 0, "failed": [MODEL_ID]}
    assert _stored_fingerprint() == old_fingerprint
    (event,) = _rekey_audit_events()
    (failure,) = event.event_metadata["failed"]
    assert failure["model_id"] == MODEL_ID
    assert "archived PDF" in failure["reason"]
    assert any(
        entry["event"] == "registry.profile_rekey_skipped" and entry["log_level"] == "warning"
        and entry["model_id"] == MODEL_ID
        for entry in logs
    )
