"""scripts/seed_demo.py against the in-memory registry + a temp work dir.

Proves the demo seeder does what the README promises without an AI key: the
corpus profiles become active, the corpus models are approved under the
fingerprint the live fingerprinter computes, and every seeded Colt invoice runs
through the real pipeline on the approved model with zero tokens.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from polaris.config import settings
from polaris.db import crud
from polaris.db.models import ExtractionJob, IntakeRecord

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "seed_demo.py"
COLT = "colt.standard.v1"
EUNETWORKS = "eunetworks.standard.v2"


def _load_seed_demo():
    spec = importlib.util.spec_from_file_location("seed_demo", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Dataclasses with postponed annotations resolve them through sys.modules.
    sys.modules["seed_demo"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def demo_env(isolated_db, tmp_path, monkeypatch):
    """Empty registry DB seeded with the disk schemas/specs, every directory under tmp."""
    from polaris.db.seed import seed_registries_from_disk

    seed_registries_from_disk()
    for attr in ("inbound_dir", "processing_dir", "completed_dir", "exceptions_dir",
                 "archive_dir", "extraction_models_dir"):
        monkeypatch.setattr(settings, attr, tmp_path / "work" / attr)
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "work_dir", tmp_path / "work")

    # Redis is not part of this test; the pipeline tolerates a missing broker
    # but would log a warning per step.
    for name in ("publish_event", "publish_completed", "publish_failed"):
        monkeypatch.setattr(f"polaris.pipeline.processor.{name}", lambda *a, **k: None)

    def no_ai(*args, **kwargs):  # pragma: no cover - the assertion is that this never runs
        raise AssertionError("the demo seeder must never reach AI extraction")

    monkeypatch.setattr("polaris.pipeline.processor.extract_invoice", no_ai)
    return tmp_path


def test_seed_demo_routes_colt_through_the_approved_model_for_free(demo_env):
    seed_demo = _load_seed_demo()
    from polaris.db.session import SessionLocal

    now = datetime(2026, 11, 3, 12, 0, 0)
    report = seed_demo.seed(now=now)

    assert report.failed == []
    assert sorted(report.profiles) == [COLT, EUNETWORKS]
    assert {action for _, action, _ in report.models} == {"approved"}

    db = SessionLocal()
    try:
        colt_intakes = list(db.scalars(select(IntakeRecord).where(IntakeRecord.supplier_profile_id == COLT)))
        assert len(colt_intakes) == 8
        assert {intake.status for intake in colt_intakes} == {"completed"}

        jobs = list(db.scalars(select(ExtractionJob).where(ExtractionJob.supplier_profile_id == COLT)))
        assert len(jobs) == 8
        assert {job.extraction_path for job in jobs} == {"model"}
        assert {job.status for job in jobs} == {"completed"}
        assert all(job.tokens_input == 0 and job.tokens_output == 0 for job in jobs)
        assert all(float(job.estimated_cost_usd or 0) == 0 for job in jobs)
        assert all(job.extraction_model_id == COLT for job in jobs)
        assert all(job.xlsx_output_path and Path(job.xlsx_output_path).is_file() for job in jobs)

        # The approved model is keyed by the fingerprint the pipeline computed.
        model = crud.find_model_by_profile(db, COLT, status="approved")
        assert model is not None
        assert {intake.layout_fingerprint for intake in colt_intakes} == {model.layout_fingerprint}
        assert model.created_from_intake in {intake.id for intake in colt_intakes}

        # Timestamps spread across the last 30 days, oldest first in corpus order.
        created = sorted(intake.created_at for intake in colt_intakes)
        assert created[0] < now - timedelta(days=14)
        assert created[-1] < now
        assert created[-1] > now - timedelta(days=seed_demo.SPREAD_DAYS)
        assert len(set(created)) == len(created)

        stats = crud.get_dashboard_stats(db)
        assert stats["model_path_count"] == len(report.processed)
        assert stats["ai_path_count"] == 0
        assert stats["approved_models"] == 2
    finally:
        db.close()

    # Delivered copies land in the profile's output folder under data_dir.
    delivered = list((demo_env / "data" / "Colt" / "xls").glob("*.xlsx"))
    assert len(delivered) == 8


def test_seed_demo_is_idempotent(demo_env):
    seed_demo = _load_seed_demo()
    from polaris.db.session import SessionLocal

    first = seed_demo.seed(layouts=("colt.standard",))
    second = seed_demo.seed(layouts=("colt.standard",))

    assert first.failed == [] and second.failed == []
    assert len(first.processed) == 8
    assert second.processed == []
    assert len(second.reused) == 8
    assert [action for _, action, _ in second.models] == ["kept"]

    db = SessionLocal()
    try:
        assert db.scalar(select(IntakeRecord.id).where(IntakeRecord.supplier_profile_id == COLT).limit(1))
        assert len(list(db.scalars(select(IntakeRecord)))) == 8
    finally:
        db.close()


def test_seed_demo_dry_run_writes_nothing(demo_env):
    seed_demo = _load_seed_demo()
    from polaris.db.session import SessionLocal

    report = seed_demo.seed(dry_run=True)

    assert len(report.processed) == 16
    assert [action for _, action, _ in report.models] == ["would approve", "would approve"]
    db = SessionLocal()
    try:
        assert list(db.scalars(select(IntakeRecord))) == []
        assert crud.find_model_by_profile(db, COLT) is None
    finally:
        db.close()
    assert not (demo_env / "data").exists()


def test_reset_requires_debug(demo_env, monkeypatch):
    seed_demo = _load_seed_demo()
    from polaris import runtime_settings

    real_runtime_value = runtime_settings.runtime_value

    def debug_is(value: bool):
        return lambda name: value if name == "debug" else real_runtime_value(name)

    monkeypatch.setattr("polaris.runtime_settings.runtime_value", debug_is(False))
    with pytest.raises(SystemExit, match="POLARIS_DEBUG"):
        seed_demo.seed(reset=True, layouts=("colt.standard",))

    monkeypatch.setattr("polaris.runtime_settings.runtime_value", debug_is(True))
    report = seed_demo.seed(reset=True, layouts=("colt.standard",))
    assert report.failed == []
    assert len(report.processed) == 8
