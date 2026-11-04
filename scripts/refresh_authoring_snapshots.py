"""Re-author the golden-corpus models with AI and refresh their model.json snapshots.

Why this exists: Suite 2 (tests/test_models/test_corpus_extraction.py) runs the
committed ``tests/fixtures/corpus/<layout>/model.json`` on every PDF of its
layout. When the authoring prompt, the interpreter vocabulary or a corpus
profile changes, those snapshots have to be authored again. This script runs the
same loop as ``pytest -m authoring`` (tests/test_models/test_corpus_authoring.py),
step for step, for each layout with a ``profile.json``:

1. serve the committed fixture profile for its id (no registry row needed);
2. AI-extract the first PDF and normalise it into the ground truth;
3. author a model in the grounded loop (author -> execute -> diff against the
   profile's delivery columns -> re-author with the diff as feedback), up to
   ``POLARIS_MODEL_AUTHORING_MAX_ATTEMPTS``;
4. execute the result on every corpus PDF and compare with the expected
   deliverables (``expected/*.xlsx`` or ``expected_line_items.json``).

``model.json`` is written only when every invoice reproduces. The exit code is
non-zero when any layout fails. Review the diff before committing.

The AI provider comes from the normal settings path: the ``llm_provider``
runtime setting saved in the database, else ``POLARIS_LLM_PROVIDER``, picks
openai or anthropic (model names resolve the same way), and the key is the stored ``provider_credentials`` row (needs
``POLARIS_SECRET_KEY``) or else ``POLARIS_OPENAI_API_KEY`` /
``POLARIS_ANTHROPIC_API_KEY``. It stops before any AI call when that provider
has no key, and an extraction/authoring model name from the other provider's
catalogue (the env defaults are OpenAI's) is replaced by this provider's
default model. Two ways to run it (from the repo root; set
``PYTHONUTF8=1`` on Windows):

    # 1. Key from the environment, throwaway SQLite registry (what CI does)
    POLARIS_LLM_PROVIDER=anthropic POLARIS_ANTHROPIC_API_KEY=sk-ant-... \\
        python scripts/refresh_authoring_snapshots.py --scratch-db

    # 2. Key stored in an existing database's provider_credentials
    POLARIS_DATABASE_URL=mysql+pymysql://stencil:stencil@127.0.0.1:3308/stencil_demo \\
    POLARIS_SECRET_KEY=<the Fernet key that database was written with> \\
        python scripts/refresh_authoring_snapshots.py

Mode 2 only reads the database (runtime settings and the stored key); the
script writes no rows. Options:

    --only colt.standard     re-author one layout (repeatable)
    --dry-run                author and verify, but do not write model.json
    --work-dir PATH          scratch work dir (AI debug dumps etc.; default: a new temp dir)
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))  # tests.corpus_utils / tests.test_models helpers

from polaris.config import settings  # noqa: E402
from polaris.extraction import extractor  # noqa: E402
from polaris.extraction.evidence import build_model_authoring_evidence  # noqa: E402
from polaris.extraction.extractor import build_canonical_invoice, extract_invoice  # noqa: E402
from polaris.extraction.layout import extract_layout_document, render_layout_text  # noqa: E402
from polaris.extraction.normalization import apply_layout_profile_hints  # noqa: E402
from polaris.fingerprint.fingerprinter import compute_layout_family_key, fingerprint_pdf  # noqa: E402
from polaris.models.authoring import author_extraction_model  # noqa: E402
from polaris.models.diff import diff_invoices  # noqa: E402
from polaris.models.interpreter import execute_model  # noqa: E402
from polaris.models.training import _normalize_line_items  # noqa: E402
from polaris.output.xlsx_writer import build_output_rows  # noqa: E402
from polaris.profiles import loader as profiles_loader  # noqa: E402
from polaris.profiles.contract import delivery_columns  # noqa: E402
from tests.corpus_utils import CorpusLayout, discover_layouts  # noqa: E402
from tests.test_models.test_corpus_extraction import _compare_to_summary, _compare_to_xlsx  # noqa: E402


@dataclass
class LayoutResult:
    layout_id: str
    ok: bool
    message: str


def _configure_work_dir(work_dir: Path) -> None:
    """Point every operational directory at the scratch work dir."""
    work_dir.mkdir(parents=True, exist_ok=True)
    settings.work_dir = work_dir
    settings.inbound_dir = work_dir / "inbound"
    settings.processing_dir = work_dir / "processing"
    settings.completed_dir = work_dir / "completed"
    settings.exceptions_dir = work_dir / "exceptions"
    settings.archive_dir = work_dir / "archive"
    settings.extraction_models_dir = work_dir / "extraction_models"


def _use_scratch_db(work_dir: Path) -> Path:
    """Rebind the DB session to a fresh SQLite file so no MySQL is needed."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from polaris.db import session as db_session
    from polaris.db.models import Base

    path = work_dir / "authoring.sqlite"
    path.unlink(missing_ok=True)
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    Base.metadata.create_all(engine)
    # Callers import SessionLocal lazily, so rebinding the attribute is enough.
    db_session.engine = engine
    db_session.SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    return path


def _preflight_provider() -> str | None:
    """Check the active provider has a key and a model of its own; return an error or None.

    The extraction/authoring model names default to OpenAI's. With
    ``POLARIS_LLM_PROVIDER=anthropic`` and no saved runtime settings they would be
    sent to Claude as-is, so a name from the other provider's catalogue is swapped
    for this provider's default.
    """
    from polaris import runtime_settings, secrets
    from polaris.llm.client import active_provider
    from polaris.llm.config import PROVIDER_MODELS, default_model

    provider = active_provider()
    if not secrets.get_provider_key(provider):
        return (f"no {provider} API key: set POLARIS_{provider.upper()}_API_KEY, or store one in Settings "
                "and run against that database with its POLARIS_SECRET_KEY")
    foreign = {m for p, models in PROVIDER_MODELS.items() if p != provider for m in models}
    names = ("openai_model_extraction", "openai_model_model_generation")
    for name in names:
        if runtime_settings.runtime_value(name) in foreign:
            setattr(settings, name, default_model(provider))
    runtime_settings.get_runtime_settings(force_refresh=True)
    for name in names:
        model = runtime_settings.runtime_value(name)
        if model in foreign:
            return f"{name} is {model!r}, a model of another provider than {provider}; change it in Settings"
    print(f"Provider: {provider} (extraction {runtime_settings.runtime_value(names[0])}, "
          f"authoring {runtime_settings.runtime_value(names[1])})")
    return None


@contextmanager
def _serve_fixture_profile(profile) -> Iterator[None]:
    """Make the profile loaders return the committed fixture profile for its id."""
    original = profiles_loader.get_profile

    def get_profile(profile_id: str):
        if profile_id == profile.profile_id:
            return profile
        return original(profile_id)

    profiles_loader.get_profile = get_profile
    extractor.get_profile = get_profile
    try:
        yield
    finally:
        profiles_loader.get_profile = original
        extractor.get_profile = original


def _ai_ground_truth(profile, pdf: Path, fingerprint: str):
    """AI-extract one training invoice exactly like the training pipeline does."""
    extraction_result = extract_invoice(
        pdf,
        supplier_name=profile.identity.canonical_name,
        output_type=profile.classification.output_type,
        supplier_profile_id=profile.profile_id,
    )
    invoice = build_canonical_invoice(
        raw_data=extraction_result.raw_data,
        intake_id=f"corpus-authoring-{pdf.stem}",
        extraction_result=extraction_result,
        output_type=profile.classification.output_type,
        supplier_profile_id=profile.profile_id,
        layout_fingerprint=fingerprint,
    )
    document = extract_layout_document(pdf)
    apply_layout_profile_hints(invoice, document, profile, profile.line_item_hints)
    _normalize_line_items(invoice, keep_zero_amount=profile.include_zero_amount_line_items)
    return invoice, document


def _author(profile, training_pdf: Path):
    """Run the grounded authoring loop; return (model, None) or (None, failure text)."""
    fingerprint, features = fingerprint_pdf(training_pdf)
    layout_family_key = compute_layout_family_key(
        features,
        supplier=profile.identity.canonical_name,
        output_type=profile.classification.output_type,
    )

    ai_invoice, document = _ai_ground_truth(profile, training_pdf, fingerprint)
    if not ai_invoice.line_items:
        return None, "AI extraction returned no line items"

    page_texts = render_layout_text(document)
    layout_evidence = build_model_authoring_evidence(document, ai_invoice)
    max_attempts = max(settings.model_authoring_max_attempts, 1)

    feedback = None
    model = None
    last_diff = None
    for attempt in range(1, max_attempts + 1):
        print(f"  attempt {attempt}/{max_attempts}", flush=True)
        auth = author_extraction_model(
            page_texts=page_texts,
            layout_evidence=layout_evidence,
            ai_invoice=ai_invoice,
            profile=profile,
            fingerprint=fingerprint,
            layout_family_key=layout_family_key,
            intake_id=f"corpus-authoring-{training_pdf.stem}",
            feedback=feedback,
        )
        model = auth.model
        try:
            model_invoice = execute_model(model, training_pdf, ai_invoice.intake_id, document=document)
        except Exception as exc:
            feedback = f"EXECUTION ERROR: the rules failed to run: {exc}"
            last_diff = None
            continue
        _normalize_line_items(model_invoice, keep_zero_amount=profile.include_zero_amount_line_items)
        last_diff = diff_invoices(ai_invoice, model_invoice, delivery_columns(profile))
        if last_diff.is_match:
            return model, None
        feedback = last_diff.feedback()

    if model is None:
        return None, "authoring produced no model"
    return None, (
        f"authoring did not converge after {max_attempts} attempt(s):\n"
        + (last_diff.summary() if last_diff else feedback or "unknown error")
    )


def _generalization_failures(layout: CorpusLayout, profile, model) -> list[str]:
    """Execute the model on every corpus PDF and compare with the expectations."""
    summary = (
        layout.load_summary_expectations().get("invoices", {})
        if layout.summary_expectations_path.exists()
        else {}
    )
    failures: list[str] = []
    for pdf in layout.pdfs:
        invoice = execute_model(model, pdf, intake_id=f"corpus-{pdf.stem}")
        _normalize_line_items(invoice, keep_zero_amount=profile.include_zero_amount_line_items)
        rows = build_output_rows(invoice, delivery_columns(profile))
        if layout.expected_xlsx_for(pdf).exists():
            errors = _compare_to_xlsx(layout, pdf, rows)
        elif pdf.name in summary:
            errors = _compare_to_summary(summary[pdf.name], rows)
        else:
            continue
        if errors:
            failures.append(f"{pdf.name}:\n  " + "\n  ".join(errors))
    return failures


def refresh_layout(layout: CorpusLayout, *, dry_run: bool) -> LayoutResult:
    """Author, verify and (unless dry run) write one layout's model.json."""
    profile = layout.load_profile()
    with _serve_fixture_profile(profile):
        model, error = _author(profile, layout.pdfs[0])
        if model is None:
            return LayoutResult(layout.layout_id, False, error or "authoring failed")
        failures = _generalization_failures(layout, profile, model)
    if failures:
        return LayoutResult(
            layout.layout_id, False, "authored model does not generalize:\n" + "\n".join(failures)
        )
    reproduced = f"reproduces all {len(layout.pdfs)} invoice(s)"
    if dry_run:
        return LayoutResult(layout.layout_id, True, f"{reproduced}; dry run, not written")
    layout.model_path.write_text(
        json.dumps(model.model_dump(mode="json"), indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return LayoutResult(layout.layout_id, True, f"{reproduced}; wrote {layout.model_path}")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", action="append", default=[], metavar="LAYOUT",
                        help="corpus layout folder to re-author (repeatable; default: every layout with a profile)")
    parser.add_argument("--dry-run", action="store_true", help="author and verify, but do not write model.json")
    parser.add_argument("--work-dir", type=Path, default=None,
                        help="scratch work dir for AI debug dumps etc. (default: a new temp dir)")
    parser.add_argument("--scratch-db", action="store_true",
                        help="use a throwaway SQLite registry in the work dir instead of POLARIS_DATABASE_URL")
    args = parser.parse_args(argv)

    layouts = [layout for layout in discover_layouts() if layout.profile_path.exists()]
    if args.only:
        known = {layout.layout_id for layout in layouts}
        unknown = sorted(set(args.only) - known)
        if unknown:
            print(f"Unknown layout(s): {', '.join(unknown)}. Known: {', '.join(sorted(known)) or 'none'}")
            return 2
        layouts = [layout for layout in layouts if layout.layout_id in args.only]
    if not layouts:
        print("No corpus layouts with a profile.json and invoices.")
        return 2

    work_dir = args.work_dir or Path(tempfile.mkdtemp(prefix="polaris-authoring-"))
    _configure_work_dir(work_dir.resolve())
    print(f"Work dir: {settings.work_dir}")
    if args.scratch_db:
        print(f"Scratch registry: {_use_scratch_db(settings.work_dir)}")
    error = _preflight_provider()
    if error:
        print(error)
        return 2

    results: list[LayoutResult] = []
    for layout in layouts:
        print(f"{layout.layout_id}: authoring from {layout.pdfs[0].name}", flush=True)
        try:
            result = refresh_layout(layout, dry_run=args.dry_run)
        except Exception as exc:
            result = LayoutResult(layout.layout_id, False, f"{type(exc).__name__}: {exc}")
        results.append(result)
        print(f"{layout.layout_id}: {'OK' if result.ok else 'FAILED'} - {result.message}", flush=True)

    failed = [r.layout_id for r in results if not r.ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} layout(s) reproduced"
          + (f"; failed: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
