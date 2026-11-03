"""Re-keying a model's layout fingerprint from its archived authoring PDF.

The routing key is (profile, fingerprint). The fingerprint depends on the
profile's fingerprint rules and on the fingerprinter, so either changing after
approval orphans the model: the pipeline computes a different hash for the
same PDF and never routes to it again. `rekey_model_fingerprint` recomputes
the hash from the source invoice so the model routes again.
"""

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from polaris.db import crud
from polaris.db.models import Base, IntakeRecord
from polaris.models import registry
from polaris.models.schema import ExtractionModel


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _isolate_fs(tmp_path, monkeypatch):
    monkeypatch.setattr(registry.settings, "extraction_models_dir", tmp_path / "models")
    monkeypatch.setattr(registry.settings, "archive_dir", tmp_path / "archive")


def _archive_pdf(intake_id: str) -> Path:
    path = registry.settings.archive_dir / intake_id / "original.pdf"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"%PDF-1.4 stub")
    return path


def _seed(db: Session, *, intake_id: str = "intake-1", with_pdf: bool = True) -> ExtractionModel:
    db.add(IntakeRecord(id=intake_id, original_filename="inv.pdf", original_pdf_path="/x/inv.pdf",
                        archive_pdf_path=f"/work/archive/{intake_id}/original.pdf", status="completed"))
    db.commit()
    if with_pdf:
        _archive_pdf(intake_id)
    model = ExtractionModel(
        model_id="colt.standard.v1", supplier_profile_id="colt.standard.v1", supplier="Colt",
        layout_fingerprint="sha256:old", layout_family_key="family:old", created_from_intake=intake_id,
    )
    registry.save_model(db, model)
    crud.update_model_status(db, model.model_id, "approved", approved_by="me")
    return model


def _stub_fingerprinter(monkeypatch, new_hash: str = "sha256:new"):
    """Stand in for pymupdf + the profile store; the test is about the re-key contract."""
    import polaris.fingerprint.fingerprinter as fp
    import polaris.profiles.loader as loader

    calls: list[tuple[Path, object]] = []

    def fake_fingerprint_pdf(pdf_path, *, profile=None, max_pages=30):
        calls.append((pdf_path, profile))
        return new_hash, object()

    monkeypatch.setattr(fp, "fingerprint_pdf", fake_fingerprint_pdf)
    monkeypatch.setattr(fp, "compute_layout_family_key", lambda features, *, supplier, output_type: "family:new")
    monkeypatch.setattr(loader, "get_profile", lambda profile_id: {"profile_id": profile_id})
    return calls


def test_dry_run_reports_the_change_without_writing(db, monkeypatch):
    _seed(db)
    calls = _stub_fingerprinter(monkeypatch)

    result = registry.rekey_model_fingerprint(db, "colt.standard.v1", apply=False)

    assert result is not None and result.error is None
    assert result.changed and not result.applied
    assert result.old_fingerprint == "sha256:old" and result.new_fingerprint == "sha256:new"
    # Recomputed from the archived original under the CURRENT archive_dir, with the profile.
    assert calls[0][0] == registry.settings.archive_dir / "intake-1" / "original.pdf"
    assert calls[0][1] == {"profile_id": "colt.standard.v1"}
    assert crud.get_extraction_model(db, "colt.standard.v1").layout_fingerprint == "sha256:old"


def test_apply_rekeys_the_record_and_keeps_status_and_rules(db, monkeypatch):
    _seed(db)
    _stub_fingerprinter(monkeypatch)
    before = crud.get_extraction_model(db, "colt.standard.v1").model_json

    result = registry.rekey_model_fingerprint(db, "colt.standard.v1", updated_by="ops")

    assert result is not None and result.applied and result.changed
    record = crud.get_extraction_model(db, "colt.standard.v1")
    assert record.layout_fingerprint == "sha256:new"
    assert record.layout_family_key == "family:new"
    assert record.status == "approved"
    assert record.updated_by == "ops"
    assert record.model_json["layout_fingerprint"] == "sha256:new"
    # Nothing but the key fields moved.
    skip = {"layout_fingerprint", "layout_family_key", "updated_by"}
    unchanged = {k: v for k, v in before.items() if k not in skip}
    assert {k: record.model_json[k] for k in unchanged} == unchanged
    # Routing now finds it under the new hash and not the old one.
    assert registry.find_approved_model(db, "colt.standard.v1", "sha256:new") is not None
    assert registry.find_approved_model(db, "colt.standard.v1", "sha256:old") is None
    # The filesystem copy follows the DB.
    assert (registry.settings.extraction_models_dir / "colt.standard.v1.json").exists()


def test_unchanged_hash_is_reported_as_such(db, monkeypatch):
    _seed(db)
    _stub_fingerprinter(monkeypatch, new_hash="sha256:old")

    result = registry.rekey_model_fingerprint(db, "colt.standard.v1")

    assert result is not None and result.applied and not result.changed


def test_missing_archive_is_a_skip_not_a_crash(db, monkeypatch):
    _seed(db, with_pdf=False)
    _stub_fingerprinter(monkeypatch)

    result = registry.rekey_model_fingerprint(db, "colt.standard.v1")

    assert result is not None and not result.applied
    assert result.error and "not found" in result.error
    assert crud.get_extraction_model(db, "colt.standard.v1").layout_fingerprint == "sha256:old"


def test_model_without_source_intake_is_skipped(db, monkeypatch):
    model = ExtractionModel(model_id="m", supplier_profile_id="m", supplier="X", layout_fingerprint="sha256:old")
    registry.save_model(db, model)
    _stub_fingerprinter(monkeypatch)

    result = registry.rekey_model_fingerprint(db, "m")

    assert result is not None and result.error and "source intake" in result.error


def test_unknown_model_returns_none(db):
    assert registry.rekey_model_fingerprint(db, "nope") is None
