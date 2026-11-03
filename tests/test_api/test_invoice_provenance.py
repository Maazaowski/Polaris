"""GET /invoices/{id}/provenance serves the package or says why there is none."""

import json

from fastapi.testclient import TestClient

from stencil.config import settings
from stencil.main import app


def test_absent_provenance_is_reported_not_404(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "completed_dir", tmp_path)

    response = TestClient(app).get("/api/v1/invoices/nothing-here/provenance")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False and "provenance" in body["reason"].lower()


def test_present_provenance_is_returned_with_available_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "completed_dir", tmp_path)
    row = {
        "row_index": 0, "line_number": 1, "page": 1, "row_ids": ["p1.r3"],
        "box": {"x0": 1, "y0": 2, "x1": 3, "y1": 4}, "fields": {},
    }
    package = {"version": 1, "approximate": False, "pages": [1], "header": {}, "totals": {}, "rows": [row]}
    (tmp_path / "abc").mkdir()
    (tmp_path / "abc" / "provenance.json").write_text(json.dumps(package), encoding="utf-8")

    response = TestClient(app).get("/api/v1/invoices/abc/provenance")

    assert response.status_code == 200
    assert response.json() == {"available": True, **package}


def test_path_traversal_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "completed_dir", tmp_path)
    assert TestClient(app).get("/api/v1/invoices/..%2Fabc/provenance").status_code in (400, 404)
