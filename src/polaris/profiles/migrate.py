"""One-shot migration of supplier profile JSON to the slim schema.

Relocates legacy top-level keys into ``advanced`` / ``delivery`` / ``notes``.
Legacy ``header_mapping`` becomes label hints on the profile's ``fields``.
Registry-era keys (``output_spec_id``, ``field_schema_id``, ``field_overrides``,
``output_mapping_overrides``) are passed through untouched so a stale file
fails loudly in ``SupplierProfile`` instead of being silently emptied; run
``scripts/embed_profile_contract.py`` on such a file first.

Idempotent: a file already in the new shape round-trips unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

from polaris.profiles.schema import _LEGACY_CONTRACT_KEYS, SupplierProfile

_HEADER_LABEL_FIELD_MAP = {
    "invoice_number_label": "invoice_number",
    "invoice_date_label": "invoice_date",
    "due_date_label": "due_date",
    "account_number_label": "account_number",
    "total_due_label": "total_due",
    "currency_label": "currency",
}


def _header_mapping_to_fields(header_mapping: dict) -> list[dict]:
    fields: list[dict] = []
    for label_key, field_name in _HEADER_LABEL_FIELD_MAP.items():
        label = header_mapping.get(label_key)
        if label:
            fields.append({"name": field_name, "scope": "document", "label_hint": label})
    return fields


def _strip_header_mapping(advanced: dict) -> dict:
    cleaned = dict(advanced)
    cleaned.pop("header_mapping", None)
    return cleaned


def migrate_profile_dict(old: dict) -> dict:
    """Return the new-shape profile dict for an old- or new-shape input."""
    legacy_header = old.get("header_mapping") or (old.get("advanced") or {}).get("header_mapping") or {}

    if "advanced" in old:
        advanced = _strip_header_mapping(old.get("advanced") or {})
        delivery = old.get("delivery") or {}
        notes = old.get("notes")
    else:
        advanced = {
            "document_structure": old.get("document_structure") or {},
            "line_item_hints": old.get("line_item_hints") or {},
            "include_zero_amount_line_items": old.get("include_zero_amount_line_items", False),
        }
        delivery = {
            "inbound_path": old.get("inbound_path"),
            "output_path": old.get("output_path"),
        }
        notes = old.get("notes") or old.get("extraction_notes") or old.get("billing_reference_hint")

    fields = list(old.get("fields") or [])
    if legacy_header:
        present = {(f.get("scope", "document"), f.get("name")) for f in fields}
        fields.extend(
            f for f in _header_mapping_to_fields(legacy_header) if ("document", f["name"]) not in present
        )

    legacy = {k: old[k] for k in _LEGACY_CONTRACT_KEYS if old.get(k)}

    return {
        "profile_id": old["profile_id"],
        "version": old.get("version", 1),
        "status": old.get("status", "draft"),
        "layout_description": old.get("layout_description"),
        "identity": old.get("identity") or {"canonical_name": old["profile_id"]},
        "classification": {"output_type": (old.get("classification") or {}).get("output_type", "standard")},
        "fields": fields,
        "output_columns": list(old.get("output_columns") or []),
        **legacy,
        "delivery": delivery,
        "notes": notes,
        "advanced": advanced,
        "layout_fingerprint": old.get("layout_fingerprint"),
        "training_config": old.get("training_config") or {},
        "owner": old.get("owner"),
        "created_date": old.get("created_date"),
        "last_updated_date": old.get("last_updated_date"),
    }


def migrate_profile_file(path: Path) -> bool:
    """Rewrite one profile JSON in place to the slim schema. Returns True on change."""
    old = json.loads(path.read_text(encoding="utf-8"))
    profile = SupplierProfile.model_validate(migrate_profile_dict(old))
    new_text = json.dumps(profile.model_dump(mode="json"), indent=2) + "\n"
    if new_text == path.read_text(encoding="utf-8"):
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def migrate_dir(directory: Path) -> list[str]:
    """Migrate every ``*.json`` profile in a directory. Returns changed file names."""
    changed: list[str] = []
    for path in sorted(directory.glob("*.json")):
        try:
            if migrate_profile_file(path):
                changed.append(path.name)
        except Exception as exc:  # noqa: BLE001 — report and continue
            print(f"  ! {path.name}: {exc}")
    return changed


if __name__ == "__main__":
    import sys

    targets = sys.argv[1:] or ["supplier_profiles"]
    for target in targets:
        p = Path(target)
        if p.is_dir():
            changed = migrate_dir(p)
            print(f"{target}: migrated {len(changed)} file(s): {', '.join(changed) or '(none)'}")
        elif p.is_file():
            print(f"{target}: {'migrated' if migrate_profile_file(p) else 'unchanged'}")
        else:
            print(f"{target}: not found")
