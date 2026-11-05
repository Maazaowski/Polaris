"""Load and cache supplier profiles from MySQL.

The DB is the source of truth (seeded from ``supplier_profiles/*.json`` on boot,
see ``db/seed.py``). Public function signatures are unchanged so consumers don't
care that storage moved from disk to the database.
"""

from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from polaris.profiles.schema import SupplierProfile

if TYPE_CHECKING:
    from polaris.models.registry import ProfileRekeySummary

logger = structlog.get_logger()

_profiles_cache: dict[str, SupplierProfile] = {}


def _row_to_profile(row) -> SupplierProfile | None:
    try:
        return SupplierProfile.model_validate(row.data)
    except Exception as e:  # pragma: no cover - defensive
        logger.error("profiles.parse_failed", profile_id=getattr(row, "profile_id", "?"), error=str(e))
        return None


def load_all_profiles(profiles_dir: Path | None = None) -> dict[str, SupplierProfile]:
    """Load all supplier profiles from the DB into the cache. Returns dict keyed
    by profile_id. ``profiles_dir`` is accepted for signature compatibility and
    ignored (storage is the database)."""
    global _profiles_cache
    from polaris.db import registry
    from polaris.db.session import SessionLocal

    db = SessionLocal()
    try:
        rows = registry.list_profiles(db)
    finally:
        db.close()

    profiles: dict[str, SupplierProfile] = {}
    for row in rows:
        profile = _row_to_profile(row)
        if profile is not None:
            profiles[profile.profile_id] = profile

    _profiles_cache = profiles
    logger.info("profiles.loaded_all", count=len(profiles))
    return profiles


def get_profile(profile_id: str) -> SupplierProfile | None:
    """Return a profile, reading its DB row fresh so cross-process edits are visible."""
    from polaris.db import registry
    from polaris.db.session import SessionLocal

    db = SessionLocal()
    try:
        row = registry.get_profile(db, profile_id)
    finally:
        db.close()

    if row is not None:
        profile = _row_to_profile(row)
        if profile is not None:
            _profiles_cache[profile_id] = profile
            return profile

    if not _profiles_cache:
        load_all_profiles()
    return _profiles_cache.get(profile_id)


def save_profile(profile: SupplierProfile, *, actor=None) -> "ProfileRekeySummary | None":
    """Persist (insert or update) a profile in the DB and refresh the cache.

    A model is routed by (profile id, layout fingerprint) and the fingerprint is
    salted by the profile's fingerprint rules, line-item anchors and field label
    hints (the document category is not part of it). Saving an edit to any of those used to orphan
    the profile's approved models silently: the pipeline computed a new hash
    for the same layout, found no model, and sent every invoice to AI with a
    layout-drift exception. So when the saved profile changes the salt, its
    non-retired models are re-keyed from their archived authoring invoices
    right here, on every write path. Returns what that did, or None when the
    edit did not touch the salt. Re-keying never fails the save.
    """
    from polaris.db import registry
    from polaris.db.session import SessionLocal

    db = SessionLocal()
    try:
        previous_row = registry.get_profile(db, profile.profile_id)
        previous = _row_to_profile(previous_row) if previous_row is not None else None
        registry.upsert_profile(
            db,
            profile_id=profile.profile_id,
            status=profile.status,
            canonical_name=profile.identity.canonical_name,
            data=profile.model_dump(mode="json"),
            actor=actor,
        )
    finally:
        db.close()
    _profiles_cache[profile.profile_id] = profile
    if previous is None:
        return None
    return _rekey_models_if_salt_changed(previous, profile, actor=actor)


def _rekey_models_if_salt_changed(
    previous: SupplierProfile, current: SupplierProfile, *, actor=None,
) -> "ProfileRekeySummary | None":
    # Imported here: the fingerprinter and the model registry sit above this
    # module in the import graph (both load profiles through it).
    from polaris.db.session import SessionLocal
    from polaris.fingerprint.fingerprinter import fingerprint_inputs_changed
    from polaris.models.registry import rekey_models_for_profile

    if not fingerprint_inputs_changed(previous, current):
        return None
    db = SessionLocal()
    try:
        return rekey_models_for_profile(db, current.profile_id, actor=actor)
    except Exception as exc:  # pragma: no cover - never block a profile save on the re-key
        logger.warning("profiles.rekey_after_save_failed", profile_id=current.profile_id, error=str(exc))
        return None
    finally:
        db.close()


def delete_profile(profile_id: str, *, actor=None) -> bool:
    from polaris.db import registry
    from polaris.db.session import SessionLocal

    db = SessionLocal()
    try:
        deleted = registry.delete_profile(db, profile_id, actor=actor)
    finally:
        db.close()
    _profiles_cache.pop(profile_id, None)
    return deleted


def _is_active(profile: SupplierProfile) -> bool:
    return profile.status == "active"


def _sort_profiles_for_selection(profiles: list[SupplierProfile]) -> list[SupplierProfile]:
    return sorted(profiles, key=lambda profile: profile.version, reverse=True)


def find_profile_by_supplier(supplier_name: str, *, active_only: bool = True) -> SupplierProfile | None:
    """Find the highest-version profile matching a supplier name or alias."""
    if not _profiles_cache:
        load_all_profiles()

    name_lower = supplier_name.lower()
    matches = []
    for profile in _profiles_cache.values():
        if active_only and not _is_active(profile):
            continue
        if profile.identity.canonical_name.lower() == name_lower:
            matches.append(profile)
            continue
        if any(alias.lower() == name_lower for alias in profile.identity.aliases):
            matches.append(profile)

    if not matches:
        return None
    return _sort_profiles_for_selection(matches)[0]


def get_active_profiles() -> list[SupplierProfile]:
    # Always re-read so watcher/worker pick up activations without a stale cache.
    load_all_profiles()
    return _sort_profiles_for_selection([p for p in _profiles_cache.values() if _is_active(p)])


def resolve_profile_path(profile: SupplierProfile, path_field: str) -> Path | None:
    """Resolve a profile's configured inbound/output directory (literal path)."""
    raw = getattr(profile, path_field, None)
    if not raw:
        return None
    return Path(raw).expanduser()


def normalize_account_path(raw: str | None) -> str | None:
    """A canonical key for comparing account inbound folders across profiles.

    Case-folds and normalizes separators (via ``os.path.normcase`` — lowercases
    on Windows, no-op on case-sensitive POSIX) so ``/data/X/pdf``, ``\\data\\X\\pdf``
    and a trailing slash all compare equal. Returns ``None`` for empty values or
    unresolved ``{...}`` templates. The folder need not exist yet.
    """
    import os

    if not raw or not raw.strip():
        return None
    if "{" in raw or "}" in raw:  # unresolved template, not a real folder
        return None
    expanded = os.path.expanduser(raw.strip())
    return os.path.normcase(os.path.normpath(os.path.abspath(expanded)))


def account_owner_index(
    *,
    statuses: set[str] | None = None,
    exclude_profile_id: str | None = None,
) -> dict[str, list[str]]:
    """Map every claimed account inbound folder -> the profile_id(s) that claim it.

    A value with more than one profile_id is a mapping conflict. ``statuses``
    filters which profiles count (e.g. only ``active``/``training`` are watched);
    ``exclude_profile_id`` drops one profile (used when validating that same
    profile so it doesn't conflict with itself).
    """
    load_all_profiles()
    index: dict[str, list[str]] = {}
    for profile in _profiles_cache.values():
        if exclude_profile_id and profile.profile_id == exclude_profile_id:
            continue
        if statuses is not None and profile.status not in statuses:
            continue
        for account in profile.effective_accounts:
            key = normalize_account_path(account.inbound_path)
            if key is None:
                continue
            index.setdefault(key, []).append(profile.profile_id)
    return index
