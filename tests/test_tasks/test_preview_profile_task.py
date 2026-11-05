"""The profile Preview Output delivers what the watcher delivers.

The preview task used to run extraction and render straight away, skipping the
profile hints every other AI path applies. For a Colt profile set to calculate
tax it showed tax allocated across rows (919.16 / 919.15) while delivery of
the same PDF computed 919.16 on both. Now the task runs the same shared
post-processing as the pipeline.
"""

from __future__ import annotations

import json
import shutil

import pytest

from polaris.config import settings
from polaris.extraction.extractor import ExtractionResult
from polaris.profiles.loader import save_profile
from tests.corpus_utils import CORPUS_ROOT

LAYOUT = "colt.standard"
PDF = CORPUS_ROOT / LAYOUT / "invoices" / "676198608_20240201.pdf"

# Two rows and a stated tax that is NOT 20% of them: the profile's calculate
# policy gives 20.00 / 10.00 from the rate, allocation of the 29.00 gives
# 19.33 / 9.67, so the assertion tells the two apart.
RAW_AI_DATA = {
    "header": {
        "supplier_name": "Colt",
        "invoice_number": "INV-1001",
        "invoice_date": "2026-01-01",
        "due_date": "2026-01-31",
        "account_number": "ACC-1",
        "currency": "GBP",
        "confidence": 0.95,
    },
    "line_items": [
        {"line_number": 1, "service_id": "SVC-1", "billing_reference": "SVC-1",
         "description": "Service A", "charge_type": "recurring", "amount": "100.00", "confidence": 0.95},
        {"line_number": 2, "service_id": "SVC-2", "billing_reference": "SVC-2",
         "description": "Service B", "charge_type": "recurring", "amount": "50.00", "confidence": 0.95},
    ],
    "subtotal": "150.00",
    "tax": "29.00",
    "tax_rate": "0.20",
    "total_due": "179.00",
    "overall_confidence": 0.95,
}


@pytest.fixture()
def preview_env(isolated_db, corpus_profile, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "work_dir", tmp_path)
    monkeypatch.setattr(settings, "processing_dir", tmp_path / "processing")

    def fake_extract_invoice(pdf_path, **kwargs):
        return ExtractionResult(raw_data=RAW_AI_DATA, ai_model_name="fake-ai", ai_calls=[{"call_type": "ai_scalars"}])

    monkeypatch.setattr("polaris.extraction.extractor.extract_invoice", fake_extract_invoice)

    def run(*, tax_output_mode: str | None, job_id: str = "job-1") -> dict:
        profile = corpus_profile(LAYOUT)
        profile.line_item_hints.tax_output_mode = tax_output_mode
        profile.line_item_hints.tax_rate_source = "invoice_tax_rate" if tax_output_mode else None
        save_profile(profile)
        pdf = tmp_path / PDF.name
        shutil.copyfile(PDF, pdf)
        from polaris.tasks.worker import preview_profile_task

        outcome = preview_profile_task(job_id, profile.profile_id, str(pdf))
        assert outcome["status"] == "done", outcome
        return json.loads((tmp_path / "previews" / f"{job_id}.json").read_text(encoding="utf-8"))

    return run


def _ext_tax(preview: dict) -> list[float]:
    columns = [c["header"] if isinstance(c, dict) else c for c in preview["columns"]]
    index = columns.index("EXT_TAX")
    return [row[index] for row in preview["rows"]]


def test_preview_delivers_the_profile_tax_policy(preview_env):
    result = preview_env(tax_output_mode="calculate")

    preview = result["preview"]
    assert result["status"] == "done"
    assert preview["extraction_path"] == "ai"
    assert preview["tax_method"] == "rate"
    assert _ext_tax(preview) == [20.0, 10.0]


def test_preview_without_a_profile_policy_still_auto_allocates(preview_env):
    preview = preview_env(tax_output_mode=None)["preview"]

    assert preview["tax_method"] == "allocated"
    assert _ext_tax(preview) == [19.33, 9.67]


def test_preview_cleans_up_its_artifacts(preview_env, tmp_path):
    preview_env(tax_output_mode="calculate", job_id="job-cleanup")

    assert not (tmp_path / "previews" / "job-cleanup").exists()
    assert not (tmp_path / PDF.name).exists()
    assert (tmp_path / "previews" / "job-cleanup.json").exists()
