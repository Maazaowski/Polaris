"""Embed each profile's field set and output columns; drop the registries.

Revision ID: 024
Revises: 023
Create Date: 2026-11-04

Field schemas and output specs were shared registries every supplier profile
pointed at by id, with per-profile "overrides" layered on top. From this
revision a profile owns its own ``fields`` (what its invoices are read for)
and ``output_columns`` (what it delivers, in order), and templates may carry
their own ``output_columns``.

``upgrade`` rewrites every stored profile to what it *resolved to* at this
revision, so nothing a supplier delivers changes:

* ``fields``: the fields the extractor actually read for the profile (the
  compact extractor's base document/row sets, every field a delivered column
  sources, every field the profile overrode, and every non-catalogue field of
  a custom schema), each carrying the profile's own hints: the override's
  printed label, date format, required flag and description. Catalogue fields
  with no override carry no label, so the catalogue default applies at run
  time exactly as the base schema did before.
* ``output_columns``: the spec's columns with the profile's mapping overrides
  applied and every path normalised to ``field.<name>`` / ``row.<name>``.

Then ``profile_authoring_sessions.output_spec_id`` / ``field_schema_id`` and
the ``field_schemas`` / ``output_specs`` tables are dropped.

This module is self-contained: the builtin standard schema and spec are
copied here as the thing legacy profiles resolved to, and nothing is imported
from ``polaris`` so the migration keeps working after that code changes.
``scripts/embed_profile_contract.py`` reuses ``embed_contract`` for JSON
fixtures on disk.

``downgrade`` recreates the tables with the builtin rows, restores the
session columns and writes ``field_overrides`` / ``output_mapping_overrides``
back. It is lossy: columns whose header is not one of the eight standard
headers cannot be expressed as an override and are dropped, as are custom
fields' structural details beyond what an override carried.
"""

from __future__ import annotations

import json
from collections import Counter

import sqlalchemy as sa
from alembic import op

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None

BUILTIN_SCHEMA_ID = "invoice.standard"
BUILTIN_SPEC_ID = "standard.8col"

_CHARGE_TYPES = ["recurring", "one_time", "tax", "fee", "credit", "adjustment", "surcharge", "usage", "unknown"]


def _f(name: str, scope: str, type_: str = "string", role: str = "none", *, required: bool = False,
       label_hint: str | None = None, enum_values: list[str] | None = None, description: str = "") -> dict:
    return {
        "name": name, "scope": scope, "type": type_, "role": role, "required": required,
        "label_hint": label_hint, "date_format": None, "enum_values": list(enum_values or []),
        "description": description,
    }


# The shipped ``invoice.standard`` schema at revision 023 (35 fields, in order).
BUILTIN_STANDARD_FIELDS: list[dict] = [
    _f("output_type", "document"),
    _f("supplier_name", "document", required=True),
    _f("supplier_aliases", "document"),
    _f("invoice_number", "document", role="identifier", required=True, label_hint="Invoice Number"),
    _f("invoice_date", "document", "date", required=True, label_hint="Invoice Date"),
    _f("due_date", "document", "date", label_hint="Due Date"),
    _f("account_number", "document", label_hint="Account Number",
       description="Customer/account number identifying the billed account."),
    _f("ban", "document", description="Secondary billing account number, when the document shows one."),
    _f("billing_period_start", "document", "date", description="Start of the billing period the invoice covers."),
    _f("billing_period_end", "document", "date", description="End of the billing period the invoice covers."),
    _f("currency", "document"),
    _f("po_number", "document"),
    _f("payment_terms", "document"),
    _f("source_page", "document", "integer"),
    _f("confidence", "document", "number"),
    _f("subtotal", "document", "currency", "subtotal"),
    _f("tax", "document", "currency", "tax"),
    _f("fees", "document", "currency"),
    _f("current_charges", "document", "currency", "subtotal"),
    _f("total_due", "document", "currency", "total", label_hint="Total Due"),
    _f("tax_rate", "document", "number", "tax_rate"),
    _f("line_number", "row", "integer", required=True),
    _f("service_id", "row", role="identifier",
       description="Per-line service/item identifier (e.g. circuit or service number, SKU, line ID)."),
    _f("billing_reference", "row", role="identifier",
       description="Per-line contract/order/billing reference, when shown separately from the service id."),
    _f("description", "row", required=True, description="Human-readable description of the charge."),
    _f("charge_type", "row", "enum", enum_values=_CHARGE_TYPES,
       description="Kind of charge; each fee/tax/credit/adjustment is its own line item."),
    _f("amount", "row", "currency", "amount", required=True,
       description="Net (pre-tax) amount for this line; numeric, no currency symbol."),
    _f("tax_amount", "row", "currency", "tax",
       description="Per-line tax amount, only when tax is itemized per line (else null)."),
    _f("currency", "row"),
    _f("billing_period_start", "row", "date"),
    _f("billing_period_end", "row", "date"),
    _f("quantity", "row", "number"),
    _f("unit_rate", "row", "currency"),
    _f("source_page", "row", "integer"),
    _f("confidence", "row", "number"),
]

# Catalogue fields the runtime knows beyond the builtin schema (so a profile
# naming them is a catalogue pick, not a custom field).
_EXTRA_CATALOGUE_KEYS = {("row", "plan_cost"), ("row", "equipment_cost"), ("row", "source_row_id")}
CATALOGUE_KEYS = {(f["scope"], f["name"]) for f in BUILTIN_STANDARD_FIELDS} | _EXTRA_CATALOGUE_KEYS
CATALOGUE_ORDER = [(f["scope"], f["name"]) for f in BUILTIN_STANDARD_FIELDS] + [
    ("row", "plan_cost"), ("row", "equipment_cost"), ("row", "source_row_id"),
]

# Fields the pipeline reads whether or not a profile lists them.
ALWAYS_ON_KEYS = {
    ("document", "output_type"), ("document", "supplier_name"), ("document", "currency"),
    ("document", "source_page"), ("document", "confidence"),
    ("row", "line_number"), ("row", "description"), ("row", "charge_type"), ("row", "amount"),
    ("row", "currency"), ("row", "source_page"), ("row", "confidence"), ("row", "source_row_id"),
}

# What the compact extractor asked the AI for at revision 023, before any
# column widening. Embedded as the profile's picks so the same fields are read.
DEFAULT_DOC_FIELDS = {
    "supplier_name", "invoice_number", "invoice_date", "due_date", "account_number", "currency",
    "subtotal", "tax", "fees", "current_charges", "total_due", "tax_rate",
}
DEFAULT_ROW_FIELDS = {"service_id", "billing_reference", "charge_type", "amount", "tax_amount"}

_BARE_TOTALS = {"subtotal", "tax", "fees", "total_due", "tax_rate", "current_charges"}

BUILTIN_STANDARD_COLUMNS: list[dict] = [
    {"header": "EXT_SERVICEID", "source": "row.service_id", "fallback": "row.billing_reference",
     "transforms": [], "width": 20, "number_format": None},
    {"header": "EXT_BILLINGREFERENCE", "source": "row.billing_reference", "fallback": "row.service_id",
     "transforms": [], "width": 20, "number_format": None},
    {"header": "EXT_DATE", "source": "field.invoice_date", "fallback": None,
     "transforms": [], "width": 14, "number_format": None},
    {"header": "formula", "source": "field.due_date", "fallback": "field.invoice_date",
     "transforms": [], "width": 14, "number_format": None},
    {"header": "EXT_AMOUNT", "source": "row.amount", "fallback": None,
     "transforms": [], "width": 14, "number_format": "#,##0.##"},
    {"header": "EXT_ACCOUNT", "source": "field.account_number", "fallback": None,
     "transforms": [], "width": 16, "number_format": None},
    {"header": "EXT_INVOICENUMBER", "source": "field.invoice_number", "fallback": None,
     "transforms": [], "width": 20, "number_format": None},
    {"header": "EXT_TAX", "source": "computed.line_tax", "fallback": None,
     "transforms": [], "width": 14, "number_format": "#,##0.00"},
]

LEGACY_KEYS = ("output_spec_id", "field_schema_id", "field_overrides", "output_mapping_overrides")


# ---------------------------------------------------------------------------
# Pure transformation
# ---------------------------------------------------------------------------


def normalize_path(path: str | None) -> str | None:
    """``header.x`` / ``line_item.x`` / bare totals to ``field.x`` / ``row.x``."""
    if not path:
        return path
    if path.startswith("header."):
        return "field." + path.removeprefix("header.")
    if path.startswith("line_item."):
        return "row." + path.removeprefix("line_item.")
    if path.startswith(("field.", "row.", "computed.")):
        return path
    return "field." + path


def _field_dicts(schema: dict | None) -> list[dict]:
    if not schema:
        return [dict(f) for f in BUILTIN_STANDARD_FIELDS]
    out = []
    for raw in schema.get("fields") or []:
        entry = _f(raw.get("name", ""), raw.get("scope", "document"), raw.get("type", "string"),
                   raw.get("role", "none"), required=bool(raw.get("required", False)),
                   label_hint=raw.get("label_hint"), enum_values=raw.get("enum_values") or [],
                   description=raw.get("description") or "")
        entry["date_format"] = raw.get("date_format")
        out.append(entry)
    return out


def merge_overrides(base_fields: list[dict], overrides: list[dict]) -> tuple[list[dict], set[tuple[str, str]]]:
    """Label-only merge, exactly as ``fields/loader.merge_field_schema`` did.

    Returns the merged list (base order, unknown overrides appended) and the
    set of merged keys an override touched.
    """
    by_key: dict[tuple[str, str], dict] = {(f["scope"], f["name"]): dict(f) for f in base_fields}
    touched: set[tuple[str, str]] = set()
    for raw in overrides or []:
        override = _f(raw.get("name", ""), raw.get("scope", "document"), raw.get("type", "string"),
                      raw.get("role", "none"), required=bool(raw.get("required", False)),
                      label_hint=raw.get("label_hint"), enum_values=raw.get("enum_values") or [],
                      description=raw.get("description") or "")
        override["date_format"] = raw.get("date_format")
        key = (override["scope"], override["name"])
        existing = by_key.get(key)
        existing_key = key
        if existing is None:
            same_name = [k for k in by_key if k[1] == override["name"]]
            if len(same_name) == 1:
                existing_key = same_name[0]
                existing = by_key[existing_key]
        if existing is None:
            by_key[key] = override
            touched.add(key)
            continue
        by_key[existing_key] = {
            **existing,
            "label_hint": override["label_hint"] or existing["label_hint"],
            "date_format": override["date_format"] or existing["date_format"],
            "description": override["description"] or existing["description"],
            "required": existing["required"] or override["required"],
            "enum_values": override["enum_values"] or existing["enum_values"],
        }
        touched.add(existing_key)
    return list(by_key.values()), touched


def resolve_columns(spec: dict | None, overrides: list[dict]) -> list[dict]:
    columns = [dict(c) for c in ((spec or {}).get("columns") or BUILTIN_STANDARD_COLUMNS)]
    header_counts = Counter(c.get("header") for c in columns)
    override_counts = Counter(o.get("output_header") for o in overrides or [])
    by_header = {
        o["output_header"]: o
        for o in overrides or []
        if override_counts[o.get("output_header")] == 1 and header_counts[o.get("output_header")] == 1
    }
    out: list[dict] = []
    for column in columns:
        override = by_header.get(column.get("header"))
        source = override["source"] if override else column.get("source", "")
        fallback = override.get("fallback") if override else column.get("fallback")
        transforms = list(override.get("transforms") or []) if override else list(column.get("transforms") or [])
        out.append({
            "header": column.get("header", ""),
            "source": normalize_path(source) or "",
            "fallback": normalize_path(fallback),
            "transforms": transforms,
            "width": int(column.get("width", 15) or 15),
            "number_format": column.get("number_format"),
        })
    return out


def _column_field_keys(columns: list[dict]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for column in columns:
        for path in (column.get("source"), column.get("fallback")):
            if not path:
                continue
            if path.startswith("field."):
                keys.add(("document", path.removeprefix("field.")))
            elif path.startswith("row."):
                keys.add(("row", path.removeprefix("row.")))
            elif path == "computed.line_tax":
                keys.update({("row", "amount"), ("row", "tax_amount"),
                             ("document", "tax_rate"), ("document", "tax"), ("document", "subtotal")})
    return keys


def embed_contract(payload: dict, field_schemas: dict[str, dict] | None = None,
                   output_specs: dict[str, dict] | None = None) -> dict:
    """Return ``payload`` with ``fields`` / ``output_columns`` embedded and the
    legacy keys removed. Pure and idempotent."""
    data = dict(payload)
    legacy_present = any(k in data for k in LEGACY_KEYS)
    if not legacy_present:
        data.setdefault("fields", [])
        data.setdefault("output_columns", [])
        return data
    if data.get("fields") or data.get("output_columns"):
        for key in LEGACY_KEYS:
            data.pop(key, None)
        data.setdefault("fields", [])
        data.setdefault("output_columns", [])
        return data

    schema = (field_schemas or {}).get(data.get("field_schema_id") or BUILTIN_SCHEMA_ID)
    spec = (output_specs or {}).get(data.get("output_spec_id") or BUILTIN_SPEC_ID)
    base_fields = _field_dicts(schema)
    merged, touched = merge_overrides(base_fields, data.get("field_overrides") or [])
    columns = resolve_columns(spec, data.get("output_mapping_overrides") or [])

    wanted: set[tuple[str, str]] = set()
    wanted.update(("document", n) for n in DEFAULT_DOC_FIELDS)
    wanted.update(("row", n) for n in DEFAULT_ROW_FIELDS)
    wanted.update(_column_field_keys(columns))
    wanted.update(touched)
    merged_keys = {(f["scope"], f["name"]) for f in merged}
    wanted.update(k for k in merged_keys if k not in CATALOGUE_KEYS)  # custom schema fields
    wanted = {k for k in wanted if k in merged_keys}
    wanted -= {k for k in ALWAYS_ON_KEYS if k not in touched}

    by_key = {(f["scope"], f["name"]): f for f in merged}
    ordered_keys = [k for k in CATALOGUE_ORDER if k in wanted] + sorted(
        k for k in wanted if k not in CATALOGUE_KEYS
    )
    fields: list[dict] = []
    for key in ordered_keys:
        merged_field = by_key[key]
        if key in CATALOGUE_KEYS:
            overridden = key in touched
            fields.append({
                "name": key[1], "scope": key[0],
                "type": merged_field["type"], "role": merged_field["role"],
                "label_hint": merged_field["label_hint"] if overridden else None,
                "date_format": merged_field.get("date_format"),
                "required": bool(merged_field["required"]) if overridden else False,
                "enum_values": [],
                "description": (merged_field.get("description") or "") if overridden else "",
            })
        else:
            fields.append(dict(merged_field))

    for key in LEGACY_KEYS:
        data.pop(key, None)
    data["fields"] = fields
    data["output_columns"] = columns
    return data


_STANDARD_HEADERS = [c["header"] for c in BUILTIN_STANDARD_COLUMNS]


def unembed_contract(payload: dict) -> dict:
    """Best-effort inverse for ``downgrade``; lossy, see the module docstring."""
    data = dict(payload)
    fields = data.pop("fields", None) or []
    columns = data.pop("output_columns", None) or []
    overrides: list[dict] = []
    for field in fields:
        key = (field.get("scope"), field.get("name"))
        custom = key not in CATALOGUE_KEYS
        if custom or field.get("label_hint") or field.get("date_format") or field.get("required") \
                or field.get("description"):
            overrides.append({
                "name": field.get("name"), "scope": field.get("scope"),
                "type": field.get("type", "string"), "role": field.get("role", "none"),
                "label_hint": field.get("label_hint"), "date_format": field.get("date_format"),
                "required": bool(field.get("required", False)),
                "enum_values": list(field.get("enum_values") or []),
                "description": field.get("description") or "",
            })
    mapping: list[dict] = []
    standard = {c["header"]: c for c in BUILTIN_STANDARD_COLUMNS}
    for column in columns:
        base = standard.get(column.get("header"))
        if base is None:
            continue
        if (column.get("source") != base["source"] or column.get("fallback") != base["fallback"]
                or list(column.get("transforms") or [])):
            mapping.append({
                "output_header": column["header"], "source": column.get("source", ""),
                "fallback": column.get("fallback"), "transforms": list(column.get("transforms") or []),
            })
    data["output_spec_id"] = BUILTIN_SPEC_ID
    data["field_schema_id"] = BUILTIN_SCHEMA_ID
    data["field_overrides"] = overrides
    data["output_mapping_overrides"] = mapping
    return data


# ---------------------------------------------------------------------------
# Alembic
# ---------------------------------------------------------------------------


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def _load_registry(table: str, id_column: str) -> dict[str, dict]:
    if table not in _tables():
        return {}
    rows = op.get_bind().execute(sa.text(f"SELECT {id_column}, data FROM {table}")).fetchall()
    out: dict[str, dict] = {}
    for row_id, data in rows:
        out[row_id] = json.loads(data) if isinstance(data, str) else dict(data or {})
    return out


def _rewrite_profiles(transform) -> None:
    bind = op.get_bind()
    if "supplier_profiles" not in _tables():
        return
    rows = bind.execute(sa.text("SELECT profile_id, data FROM supplier_profiles")).fetchall()
    for profile_id, data in rows:
        payload = json.loads(data) if isinstance(data, str) else dict(data or {})
        updated = transform(payload)
        if updated != payload:
            bind.execute(
                sa.text("UPDATE supplier_profiles SET data = :data WHERE profile_id = :pid"),
                {"data": json.dumps(updated), "pid": profile_id},
            )


def upgrade() -> None:
    field_schemas = _load_registry("field_schemas", "schema_id")
    output_specs = _load_registry("output_specs", "spec_id")
    _rewrite_profiles(lambda payload: embed_contract(payload, field_schemas, output_specs))

    session_columns = _columns("profile_authoring_sessions")
    if session_columns & {"output_spec_id", "field_schema_id"}:
        with op.batch_alter_table("profile_authoring_sessions") as batch:
            if "output_spec_id" in session_columns:
                batch.drop_column("output_spec_id")
            if "field_schema_id" in session_columns:
                batch.drop_column("field_schema_id")

    tables = _tables()
    if "output_specs" in tables:
        op.drop_table("output_specs")
    if "field_schemas" in tables:
        op.drop_table("field_schemas")


def downgrade() -> None:
    tables = _tables()
    if "field_schemas" not in tables:
        op.create_table(
            "field_schemas",
            sa.Column("schema_id", sa.String(128), primary_key=True),
            sa.Column("name", sa.String(256), nullable=True),
            sa.Column("data", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        )
    if "output_specs" not in tables:
        op.create_table(
            "output_specs",
            sa.Column("spec_id", sa.String(128), primary_key=True),
            sa.Column("name", sa.String(256), nullable=True),
            sa.Column("data", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        )
    bind = op.get_bind()
    bind.execute(
        sa.text("INSERT INTO field_schemas (schema_id, name, data) VALUES (:id, :name, :data)"),
        {"id": BUILTIN_SCHEMA_ID, "name": "Standard Invoice", "data": json.dumps({
            "schema_id": BUILTIN_SCHEMA_ID, "name": "Standard Invoice", "fields": BUILTIN_STANDARD_FIELDS,
        })},
    )
    bind.execute(
        sa.text("INSERT INTO output_specs (spec_id, name, data) VALUES (:id, :name, :data)"),
        {"id": BUILTIN_SPEC_ID, "name": "Standard (8-column)", "data": json.dumps({
            "spec_id": BUILTIN_SPEC_ID, "name": "Standard (8-column)", "columns": BUILTIN_STANDARD_COLUMNS,
        })},
    )

    session_columns = _columns("profile_authoring_sessions")
    if session_columns and not session_columns & {"output_spec_id", "field_schema_id"}:
        with op.batch_alter_table("profile_authoring_sessions") as batch:
            batch.add_column(sa.Column("output_spec_id", sa.String(128), nullable=False,
                                       server_default=BUILTIN_SPEC_ID))
            batch.add_column(sa.Column("field_schema_id", sa.String(128), nullable=False,
                                       server_default=BUILTIN_SCHEMA_ID))

    _rewrite_profiles(unembed_contract)
