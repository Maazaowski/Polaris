"""Re-key extraction models whose layout fingerprint no longer matches their source PDF.

Why this exists: a model is routed by (supplier_profile_id, layout_fingerprint).
The fingerprint is salted by the profile's fingerprint rules (not its document
category), and by the fingerprinter itself. Edit any of those after approving a
model and the stored hash stops matching what the pipeline computes for the
very same invoice - every invoice then falls through to AI with a layout-drift
exception and the model never fires. This recomputes each model's fingerprint
from the archived PDF it was authored on, using the current profile + code.

Usage (from the repo root, with ST_* pointing at the target DB and work dir):

    python scripts/refingerprint_models.py                 # dry run, all models
    python scripts/refingerprint_models.py --model colt.standard.v1
    python scripts/refingerprint_models.py --apply         # write the new hashes
    python scripts/refingerprint_models.py --status approved --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402

from polaris.db.models import ExtractionModelRecord  # noqa: E402
from polaris.db.session import SessionLocal  # noqa: E402
from polaris.models.registry import rekey_model_fingerprint  # noqa: E402


def _short(value: str | None, n: int = 18) -> str:
    return (value or "-")[:n]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", action="append", default=[], help="model id to re-key (repeatable)")
    parser.add_argument(
        "--status", action="append", default=[],
        help="only models in this status (repeatable; default: every non-retired model)",
    )
    parser.add_argument("--apply", action="store_true", help="write the recomputed fingerprints (default: dry run)")
    parser.add_argument("--by", default="refingerprint_models.py", help="recorded as updated_by")
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        query = select(ExtractionModelRecord)
        if args.model:
            query = query.where(ExtractionModelRecord.id.in_(args.model))
        if args.status:
            query = query.where(ExtractionModelRecord.status.in_(args.status))
        else:
            query = query.where(ExtractionModelRecord.status != "retired")
        ids = [r.id for r in db.execute(query).scalars().all()]
        if not ids:
            print("No models matched.")
            return 0

        mode = "APPLY" if args.apply else "DRY RUN"
        print(f"{mode}: {len(ids)} model(s)\n")
        print(f"{'model':40} {'status':18} {'stored':20} {'recomputed':20} result")
        changed = 0
        for model_id in ids:
            result = rekey_model_fingerprint(db, model_id, apply=args.apply, updated_by=args.by)
            if result is None:
                continue
            if result.error:
                outcome = f"skipped: {result.error}"
            elif result.changed:
                changed += 1
                outcome = "re-keyed" if result.applied else "would re-key"
            else:
                outcome = "unchanged"
            print(
                f"{model_id:40} {result.status:18} {_short(result.old_fingerprint):20} "
                f"{_short(result.new_fingerprint):20} {outcome}"
            )
        print(f"\n{changed} model(s) {'re-keyed' if args.apply else 'would change'}.")
        if changed and not args.apply:
            print("Re-run with --apply to write them.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
