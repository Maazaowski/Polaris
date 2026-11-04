"""DB persistence for the config registries: supplier profiles, field schemas,
output specs. Each stores the full pydantic JSON in a ``data`` column keyed by id.

The profile loader (`profiles/loader.py`) calls
these with their own short-lived session. The DB is the source of truth; disk
JSON only seeds these on boot.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from polaris.audit import append_event, audit_stamp
from polaris.clock import utcnow
from polaris.db.models import (
    ProviderCredential,
    RuntimeSettingRecord,
    SupplierProfileRecord,
    User,
)

# ── Supplier profiles ────────────────────────────────────────


def list_profiles(db: Session) -> list[SupplierProfileRecord]:
    return list(db.scalars(select(SupplierProfileRecord).where(SupplierProfileRecord.deleted_at.is_(None))).all())


def get_profile(db: Session, profile_id: str) -> SupplierProfileRecord | None:
    row = db.get(SupplierProfileRecord, profile_id)
    if row is not None and row.deleted_at is not None:
        return None
    return row


def profile_exists(db: Session, profile_id: str) -> bool:
    return get_profile(db, profile_id) is not None


def upsert_profile(
    db: Session,
    *,
    profile_id: str,
    status: str,
    canonical_name: str | None,
    data: dict[str, Any],
    actor: User | None = None,
) -> SupplierProfileRecord:
    row = db.get(SupplierProfileRecord, profile_id)
    now = utcnow()
    action = "updated"
    data = dict(data)
    audit = dict(data.get("audit") or {})
    if row is None:
        row = SupplierProfileRecord(profile_id=profile_id)
        db.add(row)
        row.created_by_user_id = actor.id if actor else None
        audit["created"] = audit_stamp(actor, now)
        action = "created"
    elif row.deleted_at is not None:
        row.deleted_at = None
        row.deleted_by_user_id = None
        row.created_by_user_id = row.created_by_user_id or (actor.id if actor else None)
        audit.setdefault("created", audit_stamp(actor, now))
        action = "restored"
    row.status = status
    row.canonical_name = canonical_name
    row.updated_by_user_id = actor.id if actor else row.updated_by_user_id
    audit["updated"] = audit_stamp(actor, now)
    data["audit"] = audit
    row.data = data
    append_event(
        db,
        entity_type="profile",
        entity_id=profile_id,
        action=action,
        actor=actor,
        metadata={"status": status, "canonical_name": canonical_name},
    )
    db.commit()
    return row


def delete_profile(db: Session, profile_id: str, *, actor: User | None = None) -> bool:
    row = get_profile(db, profile_id)
    if row is None:
        return False
    now = utcnow()
    row.deleted_at = now
    row.deleted_by_user_id = actor.id if actor else None
    data = dict(row.data or {})
    audit = dict(data.get("audit") or {})
    audit["deleted"] = audit_stamp(actor, now)
    data["audit"] = audit
    row.data = data
    append_event(db, entity_type="profile", entity_id=profile_id, action="deleted", actor=actor)
    db.commit()
    return True


# ── Field schemas ────────────────────────────────────────────


def list_runtime_settings(db: Session) -> list[RuntimeSettingRecord]:
    return list(db.scalars(select(RuntimeSettingRecord)).all())


def get_runtime_setting(db: Session, key: str) -> RuntimeSettingRecord | None:
    return db.get(RuntimeSettingRecord, key)


def upsert_runtime_setting(db: Session, *, key: str, value: dict[str, Any]) -> RuntimeSettingRecord:
    row = db.get(RuntimeSettingRecord, key)
    if row is None:
        row = RuntimeSettingRecord(key=key)
        db.add(row)
    row.value = value
    db.commit()
    return row


# Provider credentials (encrypted API keys) ----------------------------------


def get_provider_credential(db: Session, provider: str) -> ProviderCredential | None:
    return db.get(ProviderCredential, provider)


def upsert_provider_credential(db: Session, *, provider: str, key_ciphertext: str) -> ProviderCredential:
    row = db.get(ProviderCredential, provider)
    if row is None:
        row = ProviderCredential(provider=provider)
        db.add(row)
    row.key_ciphertext = key_ciphertext
    db.commit()
    return row


def delete_provider_credential(db: Session, provider: str) -> bool:
    row = db.get(ProviderCredential, provider)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True
