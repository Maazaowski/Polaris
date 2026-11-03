"""Orphan flags on model responses and the re-key endpoint."""

from fastapi.testclient import TestClient

from polaris.db import crud
from polaris.db import session as db_session
from polaris.db.models import IntakeRecord, SupplierProfileRecord
from polaris.main import app
from polaris.models import registry
from polaris.models.schema import ExtractionModel


def _seed_model(db, *, model_id: str, profile_id: str, intake_id: str | None) -> None:
    registry.save_model(
        db,
        ExtractionModel(
            model_id=model_id, supplier_profile_id=profile_id, supplier="X",
            layout_fingerprint="sha256:old", created_from_intake=intake_id,
        ),
    )


def test_list_flags_models_whose_profile_or_intake_is_gone(isolated_db, tmp_path, monkeypatch):
    monkeypatch.setattr(registry.settings, "extraction_models_dir", tmp_path)
    db = db_session.SessionLocal()
    db.add(SupplierProfileRecord(profile_id="live.profile", status="active", canonical_name="Live", data={}))
    db.add(IntakeRecord(id="intake-live", original_filename="a.pdf", original_pdf_path="/a.pdf", status="completed"))
    db.commit()
    _seed_model(db, model_id="healthy", profile_id="live.profile", intake_id="intake-live")
    _seed_model(db, model_id="no-profile", profile_id="deleted.profile", intake_id="intake-live")
    _seed_model(db, model_id="no-intake", profile_id="live.profile", intake_id="intake-purged")
    db.close()

    body = TestClient(app).get("/api/v1/models?per_page=50").json()
    flags = {m["id"]: (m["profile_missing"], m["source_intake_missing"]) for m in body["items"]}

    assert flags["healthy"] == (False, False)
    assert flags["no-profile"] == (True, False)
    assert flags["no-intake"] == (False, True)

    detail = TestClient(app).get("/api/v1/models/no-profile").json()
    assert detail["profile_missing"] is True


def test_rekey_endpoint_updates_the_fingerprint(isolated_db, tmp_path, monkeypatch):
    monkeypatch.setattr(registry.settings, "extraction_models_dir", tmp_path / "models")
    monkeypatch.setattr(registry.settings, "archive_dir", tmp_path / "archive")
    db = db_session.SessionLocal()
    db.add(SupplierProfileRecord(profile_id="p", status="active", canonical_name="P", data={}))
    db.add(IntakeRecord(id="i1", original_filename="a.pdf", original_pdf_path="/a.pdf", status="completed"))
    db.commit()
    _seed_model(db, model_id="p", profile_id="p", intake_id="i1")
    db.close()
    pdf = tmp_path / "archive" / "i1" / "original.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.4 stub")

    import polaris.fingerprint.fingerprinter as fp
    import polaris.profiles.loader as loader

    monkeypatch.setattr(fp, "fingerprint_pdf", lambda path, *, profile=None, max_pages=30: ("sha256:new", object()))
    monkeypatch.setattr(fp, "compute_layout_family_key", lambda *a, **k: "family:new")
    monkeypatch.setattr(loader, "get_profile", lambda profile_id: {"profile_id": profile_id})

    response = TestClient(app).post("/api/v1/models/p/rekey")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "model_id": "p", "changed": True, "old_fingerprint": "sha256:old", "new_fingerprint": "sha256:new",
    }
    db = db_session.SessionLocal()
    assert crud.get_extraction_model(db, "p").layout_fingerprint == "sha256:new"
    db.close()


def test_rekey_endpoint_reports_a_missing_source_as_conflict(isolated_db, tmp_path, monkeypatch):
    monkeypatch.setattr(registry.settings, "extraction_models_dir", tmp_path / "models")
    monkeypatch.setattr(registry.settings, "archive_dir", tmp_path / "archive")
    db = db_session.SessionLocal()
    _seed_model(db, model_id="p", profile_id="p", intake_id=None)
    db.close()

    response = TestClient(app).post("/api/v1/models/p/rekey")

    assert response.status_code == 409
    assert "source intake" in response.json()["detail"]
    assert TestClient(app).post("/api/v1/models/nope/rekey").status_code == 404
