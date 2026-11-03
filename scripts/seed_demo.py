"""Turn an empty Stencil database into a convincing demo in under a minute, with no AI key.

The golden corpus under ``tests/fixtures/corpus/`` holds real invoices for two
layouts plus a committed ``model.json`` that reproduces their deliverables
offline. This script loads those layouts the way an operator would have built
them up over a month:

1. the corpus profiles go into the DB through the profile loader, activated,
   each with an inbound/output folder under ``ST_DATA_DIR``;
2. each corpus model is registered and approved for its profile, keyed by the
   fingerprint the *current* fingerprinter computes for its first invoice;
3. every corpus PDF runs through the real pipeline synchronously, so it lands as
   a completed, template-path (``extraction_path == "model"``, $0) intake with an
   XLSX deliverable;
4. the intakes' timestamps are spread across the last 30 days so Insights has
   curves and the monthly breakdown has two months.

Idempotent: re-running keeps existing profiles, models and intakes and only
fills gaps. ``--reset`` (needs ``ST_DEBUG=true``) purges intakes and the
work-dir lifecycle folders first, exactly like the Settings danger-zone purge.

Usage (from the repo root, with ST_DATABASE_URL etc. pointing at the stack):

    python scripts/seed_demo.py            # fill gaps only
    python scripts/seed_demo.py --reset    # purge intakes first (ST_DEBUG only)
    python scripts/seed_demo.py --dry-run  # print the plan, write nothing
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from stencil.clock import utcnow  # noqa: E402

CORPUS_ROOT = REPO_ROOT / "tests" / "fixtures" / "corpus"
DEMO_LAYOUTS: tuple[str, ...] = ("colt.standard", "eunetworks.standard")

# Corpus invoices that cannot be a template-path success by design. The
# pipeline treats an all-zero model result as a failed extraction and falls
# back to AI, which has no key here; they stay in the corpus (the extraction
# suite still proves the model handles them) but are not seeded.
SKIPPED_PDFS: dict[str, str] = {
    "A837737 - IE-SI55765.pdf": "zero-value usage invoice (EUR 0.00); an all-zero result is not a deliverable",
}

SPREAD_DAYS = 30
SEEDED_BY = "seed_demo"
DONE_STATUSES = ("completed", "completed_with_warnings")


@dataclass
class DemoLayout:
    layout_id: str
    profile: object  # SupplierProfile
    model: object  # ExtractionModel
    pdfs: list[Path]
    skipped: list[tuple[Path, str]] = field(default_factory=list)


@dataclass
class SeedReport:
    profiles: list[str] = field(default_factory=list)
    models: list[tuple[str, str, str]] = field(default_factory=list)  # (model_id, status, fingerprint)
    processed: list[str] = field(default_factory=list)
    reused: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    purged_intakes: int = 0
    purged_dirs: int = 0


# ---------------------------------------------------------------------------
# Corpus loading
# ---------------------------------------------------------------------------


def load_layout(layout_id: str) -> DemoLayout:
    from stencil.models.schema import ExtractionModel
    from stencil.profiles.migrate import migrate_profile_dict
    from stencil.profiles.schema import SupplierProfile

    root = CORPUS_ROOT / layout_id
    profile_path = root / "profile.json"
    model_path = root / "model.json"
    if not profile_path.is_file():
        raise SystemExit(f"{layout_id}: no profile.json under {root}")
    if not model_path.is_file():
        raise SystemExit(f"{layout_id}: no model.json under {root} (nothing to approve)")

    profile = SupplierProfile.model_validate(migrate_profile_dict(json.loads(profile_path.read_text("utf-8"))))
    model = ExtractionModel.model_validate_json(model_path.read_text("utf-8"))
    pdfs: list[Path] = []
    skipped: list[tuple[Path, str]] = []
    for pdf in sorted((root / "invoices").glob("*.pdf")):
        reason = SKIPPED_PDFS.get(pdf.name)
        if reason:
            skipped.append((pdf, reason))
        else:
            pdfs.append(pdf)
    if not pdfs:
        raise SystemExit(f"{layout_id}: no invoices under {root / 'invoices'}")
    return DemoLayout(layout_id=layout_id, profile=profile, model=model, pdfs=pdfs, skipped=skipped)


def supplier_folder(profile) -> Path:
    """``<data_dir>/<CanonicalName>`` — the per-supplier root the watcher and delivery use."""
    from stencil.config import settings

    name = "".join(ch for ch in profile.identity.canonical_name if ch.isalnum() or ch in "-_")
    return settings.data_dir / (name or profile.profile_id)


# ---------------------------------------------------------------------------
# Step 1: profiles
# ---------------------------------------------------------------------------


def prepare_profile(profile) -> tuple[Path, Path]:
    """Activate the profile and point its delivery folders under ``data_dir``."""
    root = supplier_folder(profile)
    inbound, output = root / "pdf", root / "xls"
    profile.status = "active"
    profile.delivery.inbound_path = str(inbound)
    profile.delivery.output_path = str(output)
    return inbound, output


def ensure_profile(profile, *, dry_run: bool) -> None:
    from stencil.profiles.loader import save_profile

    inbound, output = prepare_profile(profile)
    if dry_run:
        return
    inbound.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    save_profile(profile)


# ---------------------------------------------------------------------------
# Step 2: approved models keyed by the current fingerprint
# ---------------------------------------------------------------------------


def compute_fingerprint(pdf: Path, profile) -> tuple[str, str]:
    from stencil.fingerprint.fingerprinter import compute_layout_family_key, fingerprint_pdf

    fingerprint, features = fingerprint_pdf(pdf, profile=profile)
    family_key = compute_layout_family_key(
        features,
        supplier=profile.identity.canonical_name,
        output_type=profile.classification.output_type,
    )
    return fingerprint, family_key


def ensure_approved_model(db, layout: DemoLayout, *, fingerprint: str, family_key: str,
                          created_from_intake: str | None) -> tuple[str, str]:
    """Register the corpus model as approved for its profile. Returns (model_id, action)."""
    from stencil.db import crud
    from stencil.models.registry import approve_model, save_model
    from stencil.models.schema import ModelStatus

    profile_id = layout.profile.profile_id
    existing = crud.find_model_by_profile(db, profile_id, status="approved")
    if existing is not None:
        if existing.layout_fingerprint == fingerprint:
            return existing.id, "kept"
        # Re-key in place: the rules are fine, only the hash drifted (profile
        # rules or fingerprinter changed since it was approved). Same effect as
        # the registry re-key, scoped to a PDF we hold in hand.
        model_json = dict(existing.model_json or {})
        model_json["layout_fingerprint"] = fingerprint
        model_json["layout_family_key"] = family_key
        existing.layout_fingerprint = fingerprint
        existing.layout_family_key = family_key
        existing.model_json = model_json
        existing.updated_by = SEEDED_BY
        db.commit()
        return existing.id, "rekeyed"

    model = layout.model.model_copy(deep=True)
    model.supplier_profile_id = profile_id
    model.status = ModelStatus.CANDIDATE
    model.layout_fingerprint = fingerprint
    model.layout_family_key = family_key
    model.created_from_intake = created_from_intake or model.created_from_intake
    model.approved_by = None
    model.approved_at = None
    saved = save_model(db, model)
    if not approve_model(db, saved.model_id, approved_by=SEEDED_BY):
        raise RuntimeError(f"could not approve model {saved.model_id}")
    return saved.model_id, "approved"


# ---------------------------------------------------------------------------
# Step 3: run the real pipeline
# ---------------------------------------------------------------------------


def existing_intake_for(db, pdf: Path, profile_id: str):
    from sqlalchemy import select

    from stencil.db.models import IntakeRecord

    stmt = (
        select(IntakeRecord)
        .where(
            IntakeRecord.original_filename == pdf.name,
            IntakeRecord.supplier_profile_id == profile_id,
            IntakeRecord.status.in_(DONE_STATUSES),
        )
        .order_by(IntakeRecord.created_at.desc())
    )
    return db.scalars(stmt).first()


def ingest(db, pdf: Path, profile_id: str) -> str:
    """Register the PDF as a watcher intake (the corpus file is copied, never moved)."""
    from stencil.intake.service import process_new_pdf

    return process_new_pdf(db, pdf, intake_source="watcher", supplier_profile_id=profile_id)


def disable_live_events() -> None:
    """Run the pipeline without Redis.

    Live events and cancel checks exist for the UI's WebSocket while a worker
    processes an upload; nobody is watching a seed, and when Redis is down each
    publish spends seconds failing to connect, which turns a 20-second seed into
    a ten-minute one.
    """
    from stencil.pipeline import processor

    def _noop(*args, **kwargs) -> None:
        return None

    for name in ("publish_event", "publish_completed", "publish_failed", "clear_cancel", "check_cancelled"):
        setattr(processor, name, _noop)


def run_pipeline(db, intake_id: str, profile_id: str) -> str | None:
    """Run steps 2-6 synchronously. Returns an error message on failure, else None."""
    from stencil.pipeline.processor import continue_pipeline

    try:
        continue_pipeline(db, intake_id, profile_id=profile_id, mode="production")
    except Exception as exc:  # the pipeline already marked the intake failed
        return f"{type(exc).__name__}: {exc}"
    return None


# ---------------------------------------------------------------------------
# Step 4: timestamps across the last 30 days
# ---------------------------------------------------------------------------


def spread_timestamps(db, intake_ids: list[str], *, now: datetime | None = None,
                      days: int = SPREAD_DAYS, seed: int = 20261103) -> None:
    """Move each intake (and its jobs/logs) to a distinct moment in the last ``days`` days.

    Deterministic (seeded) so the demo looks the same on every machine. Every
    row that belongs to an intake is shifted by the same delta, so "Received"
    still precedes "Started" and "Completed" in the invoice detail.
    """
    from sqlalchemy import select

    from stencil.db.models import ExtractionJob, IntakeRecord, ProcessingLog

    if not intake_ids:
        return
    reference = now or utcnow()  # DB timestamps are naive UTC (stencil.clock)
    rng = random.Random(seed)
    # Oldest first so the queue order follows the corpus order.
    offsets = sorted((rng.uniform(0.5, days - 0.5) for _ in intake_ids), reverse=True)

    for intake_id, offset in zip(intake_ids, offsets, strict=True):
        intake = db.get(IntakeRecord, intake_id)
        if intake is None or intake.created_at is None:
            continue
        target = reference - timedelta(days=offset)
        delta = target - intake.created_at
        intake.created_at = target
        intake.updated_at = (intake.updated_at or intake.created_at) + delta
        for job in db.scalars(select(ExtractionJob).where(ExtractionJob.intake_id == intake_id)):
            for column in ("created_at", "started_at", "completed_at"):
                value = getattr(job, column)
                if value is not None:
                    setattr(job, column, value + delta)
        for log in db.scalars(select(ProcessingLog).where(ProcessingLog.intake_id == intake_id)):
            if log.timestamp is not None:
                log.timestamp = log.timestamp + delta
    db.commit()


# ---------------------------------------------------------------------------
# Reset (same code path as DELETE /api/v1/invoices/purge)
# ---------------------------------------------------------------------------


def reset_intakes(db) -> tuple[int, int]:
    from stencil import runtime_settings
    from stencil.db import crud
    from stencil.intake.cleanup import purge_work_dir_artifacts

    if not bool(runtime_settings.runtime_value("debug")):
        raise SystemExit("--reset needs ST_DEBUG=true (it purges every intake, like the Settings danger zone)")
    deleted = crud.purge_all_intakes(db)
    removed = purge_work_dir_artifacts()
    return deleted, removed


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def seed(*, reset: bool = False, dry_run: bool = False, layouts: tuple[str, ...] = DEMO_LAYOUTS,
         now: datetime | None = None) -> SeedReport:
    from stencil.config import settings
    from stencil.db.session import SessionLocal

    report = SeedReport()
    demo_layouts = [load_layout(layout_id) for layout_id in layouts]

    db = SessionLocal()
    try:
        if reset:
            if dry_run:
                print("would purge every intake and the work-dir lifecycle folders")
            else:
                report.purged_intakes, report.purged_dirs = reset_intakes(db)

        if not dry_run:
            settings.ensure_directories()
            # The API seeds the field schema / output spec on boot; a database the
            # API has never started against needs them before the output step.
            from stencil.db.seed import seed_registries_from_disk

            seed_registries_from_disk()
            disable_live_events()

        for layout in demo_layouts:
            profile = layout.profile
            ensure_profile(profile, dry_run=dry_run)
            report.profiles.append(profile.profile_id)
            for pdf, reason in layout.skipped:
                report.skipped.append((pdf.name, reason))

            # The first invoice is the model's authoring sample: ingest it first so
            # the approved model points at a real archived intake, then key the
            # model by the fingerprint the pipeline is about to compute for it.
            first_pdf = layout.pdfs[0]
            fingerprint, family_key = compute_fingerprint(first_pdf, profile)
            if dry_run:
                report.models.append((layout.model.model_id, "would approve", fingerprint))
                for pdf in layout.pdfs:
                    report.processed.append(pdf.name)
                continue

            processed_this_run: list[str] = []
            first_existing = existing_intake_for(db, first_pdf, profile.profile_id)
            if first_existing is not None:
                first_intake_id = first_existing.id
            else:
                first_intake_id = ingest(db, first_pdf, profile.profile_id)
            model_id, action = ensure_approved_model(
                db, layout, fingerprint=fingerprint, family_key=family_key, created_from_intake=first_intake_id,
            )
            report.models.append((model_id, action, fingerprint))

            for pdf in layout.pdfs:
                if pdf is first_pdf and first_existing is None:
                    intake_id = first_intake_id
                else:
                    existing = existing_intake_for(db, pdf, profile.profile_id)
                    if existing is not None:
                        report.reused.append(pdf.name)
                        continue
                    intake_id = ingest(db, pdf, profile.profile_id)
                error = run_pipeline(db, intake_id, profile.profile_id)
                if error:
                    report.failed.append((pdf.name, error))
                else:
                    report.processed.append(pdf.name)
                processed_this_run.append(intake_id)

            spread_timestamps(db, processed_this_run, now=now)
    finally:
        db.close()
    return report


def summarize(report: SeedReport, *, dry_run: bool) -> str:
    from stencil.config import settings
    from stencil.db import crud
    from stencil.db.models import ExtractionJob, IntakeRecord
    from stencil.db.session import SessionLocal

    lines: list[str] = []
    if dry_run:
        lines.append("DRY RUN - nothing was written")
    if report.purged_intakes or report.purged_dirs:
        lines.append(f"Purged {report.purged_intakes} intake(s) and {report.purged_dirs} work folder(s)")

    lines.append("Profiles:")
    for profile_id in report.profiles:
        lines.append(f"  {profile_id}: active")
    lines.append("Models:")
    for model_id, action, fingerprint in report.models:
        lines.append(f"  {model_id}: approved ({action}, {fingerprint[:19]}...)")

    if dry_run:
        lines.append(f"Would process {len(report.processed)} invoice(s) through the pipeline")
    else:
        db = SessionLocal()
        try:
            from sqlalchemy import func, select

            counts = db.execute(
                select(IntakeRecord.status, func.count()).group_by(IntakeRecord.status)
            ).all()
            model_path = db.scalar(
                select(func.count()).select_from(ExtractionJob).where(ExtractionJob.extraction_path == "model")
            ) or 0
            stats = crud.get_dashboard_stats(db)
        finally:
            db.close()
        lines.append("Intakes by status:")
        for status, count in sorted(counts):
            lines.append(f"  {status}: {count}")
        lines.append(
            f"This run: {len(report.processed)} processed, {len(report.reused)} already seeded, "
            f"{len(report.failed)} failed"
        )
        lines.append(f"Ran free (template path, $0): {model_path} invoice(s); "
                     f"approved models: {stats['approved_models']}")
    for name, reason in report.skipped:
        lines.append(f"  skipped {name}: {reason}")
    for name, error in report.failed:
        lines.append(f"  FAILED {name}: {error}")
    lines.append(f"Supplier folders under: {settings.data_dir.resolve()}")
    lines.append(f"Open: {settings.frontend_url.rstrip('/')}/invoices")
    return "\n".join(lines)


def _quiet_logging() -> None:
    """Library logs are JSON structlog lines; keep the console to the summary."""
    import structlog

    logging.basicConfig(level=logging.WARNING)
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--reset", action="store_true",
                        help="purge every intake and the work-dir lifecycle folders first (needs ST_DEBUG=true)")
    parser.add_argument("--dry-run", action="store_true", help="print what would happen, write nothing")
    parser.add_argument("--verbose", action="store_true", help="keep the pipeline's structured logs")
    args = parser.parse_args(argv)

    if not args.verbose:
        _quiet_logging()
    started = datetime.now()
    report = seed(reset=args.reset, dry_run=args.dry_run)
    print(summarize(report, dry_run=args.dry_run))
    print(f"Done in {(datetime.now() - started).total_seconds():.1f}s")
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
