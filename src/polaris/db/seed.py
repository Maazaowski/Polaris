"""Seed the supplier-profile table from committed disk JSON (import-if-not-exists).

The DB is the source of truth. On boot we import any disk profile whose id is
not already in the DB, so a fresh deployment is populated and newly committed
profiles are picked up on later deploys, without ever overwriting a row that
was edited at runtime through the UI.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import structlog
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError

from polaris.config import settings
from polaris.db import registry

logger = structlog.get_logger()


def _iter_json(directory: Path) -> Iterator[tuple[Path, dict]]:
    if not directory.exists():
        return
    for path in sorted(directory.glob("*.json")):
        try:
            yield path, json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:  # pragma: no cover - defensive
            logger.error("seed.read_failed", path=str(path), error=str(e))


def seed_registries_from_disk() -> dict[str, int]:
    """Import committed disk JSON into the registry tables where the id is missing.
    Idempotent and safe to call from multiple processes (duplicate inserts are
    swallowed). Returns the per-registry insert counts."""
    from polaris.db.session import SessionLocal
    from polaris.profiles.migrate import migrate_profile_dict
    from polaris.profiles.schema import SupplierProfile

    inserted = {"profiles": 0}
    db = SessionLocal()
    try:
        for path, raw in _iter_json(settings.supplier_profiles_dir):
            try:
                profile = SupplierProfile.model_validate(migrate_profile_dict(raw))
            except Exception as e:
                logger.error("seed.profile_invalid", path=str(path), error=str(e))
                continue
            if registry.profile_exists(db, profile.profile_id):
                continue
            try:
                registry.upsert_profile(
                    db, profile_id=profile.profile_id, status=profile.status,
                    canonical_name=profile.identity.canonical_name,
                    data=profile.model_dump(mode="json"),
                )
                inserted["profiles"] += 1
            except IntegrityError:  # pragma: no cover - concurrent boot
                db.rollback()

    except (OperationalError, ProgrammingError) as e:
        # Tables not migrated yet (e.g. a process booted before the backend ran
        # alembic). Defer — the authoritative seed runs in the backend lifespan.
        logger.warning("seed.tables_not_ready", error=str(e))
        db.rollback()
    finally:
        db.close()

    logger.info("seed.completed", **inserted)
    return inserted
