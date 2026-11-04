"""Missing printed date formats block entering training/active, not editing.

Profiles migrated from the shared registries deliver dates without a printed
format. When every save of such an active profile was refused, none of the
supplier's other settings could be changed until someone filled the formats
in. A save that keeps the status now goes through and reports the gap as a
warning; moving into training or active still refuses.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from polaris.main import app
from polaris.profiles.loader import get_profile, save_profile
from polaris.profiles.schema import SupplierProfile

LAYOUT = "colt.standard"
DATE_WARNING = "Mapped date field 'field.invoice_date' requires an explicit printed date format."


@pytest.fixture()
def active_without_formats(isolated_db, corpus_profile) -> SupplierProfile:
    profile = corpus_profile(LAYOUT)
    profile.status = "active"
    for field in profile.fields:
        if field.type == "date":
            field.date_format = None
    save_profile(profile)
    return profile


def _put(profile: SupplierProfile):
    return TestClient(app).put(f"/api/v1/profiles/{profile.profile_id}", json=profile.model_dump(mode="json"))


def test_saving_an_active_profile_without_date_formats_succeeds_with_a_warning(active_without_formats):
    profile = active_without_formats
    profile.identity.canonical_name = "Colt Technology Services"

    response = _put(profile)

    assert response.status_code == 200, response.text
    assert DATE_WARNING in response.json()["warnings"]
    assert get_profile(profile.profile_id).identity.canonical_name == "Colt Technology Services"


def test_a_save_with_every_date_format_reports_no_warning(active_without_formats):
    profile = active_without_formats
    for field in profile.fields:
        if field.type == "date":
            field.date_format = "%d-%b-%Y"

    response = _put(profile)

    assert response.status_code == 200, response.text
    assert response.json()["warnings"] == []


def test_activating_through_a_save_still_requires_date_formats(active_without_formats):
    profile = active_without_formats
    profile.status = "draft"
    save_profile(profile)
    profile.status = "active"

    response = _put(profile)

    assert response.status_code == 422
    assert DATE_WARNING in response.json()["detail"]["issues"]


def test_retraining_an_active_profile_still_requires_date_formats(active_without_formats):
    response = TestClient(app).post(f"/api/v1/profiles/{active_without_formats.profile_id}/start-training")

    assert response.status_code == 422, response.text
    assert DATE_WARNING in response.json()["detail"]["issues"]


def test_validate_still_lists_the_missing_formats(active_without_formats):
    response = TestClient(app).post(f"/api/v1/profiles/{active_without_formats.profile_id}/validate")

    assert response.status_code == 200
    assert DATE_WARNING in response.json()["issues"]
