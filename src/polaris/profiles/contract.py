"""What a supplier profile reads and what it delivers.

This is the only place the pipeline asks those two questions. A profile owns
its own ``fields`` (picks from the catalogue, plus custom fields, each with
per-supplier hints) and its own ordered ``output_columns``. A template drawn in
the builder may carry its own ``output_columns``; when it does, they win over
the profile's. Nothing here falls back to a hidden default column set: a
profile with no columns delivers nothing until its user adds some, and an
invoice with no profile at all gets the raw extraction workbook instead.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from typing import Any

from polaris.fields.catalogue import (
    ALWAYS_ON_KEYS,
    CANONICAL_FIELDS,
    COMPUTED_SOURCES,
    catalogue_by_key,
    default_field_set,
    field_path,
)
from polaris.fields.schema import FieldDef, FieldRole, FieldSchema, FieldScope, FieldType
from polaris.output.columns import OutputColumn
from polaris.output.mapper import ColumnDef, normalize_source_path

__all__ = [
    "ContractIssue",
    "columns_to_defs",
    "date_format_issues",
    "default_field_set",
    "delivery_columns",
    "field_set",
    "output_columns",
    "raw_workbook_columns",
    "suggest_columns_from_headers",
    "validate_fields",
    "validate_output_columns",
]

_CUSTOM_NAME = re.compile(r"^[a-z][a-z0-9_]*$")

ContractIssue = str


# ---------------------------------------------------------------------------
# Fields
# ---------------------------------------------------------------------------


def _coerce_field(raw: FieldDef | dict[str, Any]) -> FieldDef:
    return raw if isinstance(raw, FieldDef) else FieldDef.model_validate(raw)


def _profile_fields(profile: Any) -> list[FieldDef]:
    return [_coerce_field(f) for f in (getattr(profile, "fields", None) or [])]


def resolve_field(field: FieldDef) -> FieldDef:
    """A catalogue pick takes its structural contract (type, role, enum values)
    from the catalogue; the profile supplies only hints. A custom field is
    taken as written."""
    base = catalogue_by_key().get((field.scope, field.name))
    if base is None:
        return field
    return base.model_copy(update={
        "label_hint": field.label_hint if field.label_hint is not None else base.label_hint,
        "date_format": field.date_format or base.date_format,
        "required": base.required or field.required,
        "description": field.description or base.description,
    })


def field_set(profile: Any) -> FieldSchema:
    """The fields this profile reads: the always-on catalogue fields merged with
    the profile's own list (profile entry wins for hints), catalogue order first
    and custom fields after. ``None`` means the whole catalogue."""
    if profile is None:
        return default_field_set()
    picks = _profile_fields(profile)
    if not picks:
        legacy = _legacy_field_set(profile)
        if legacy is not None:
            return legacy
    by_key: dict[tuple[FieldScope, str], FieldDef] = {}
    catalogue = catalogue_by_key()
    for key in ALWAYS_ON_KEYS:
        by_key[key] = catalogue[key].model_copy()
    for pick in picks:
        by_key[(pick.scope, pick.name)] = resolve_field(pick)
    ordered: list[FieldDef] = []
    for base in CANONICAL_FIELDS:
        key = (base.scope, base.name)
        if key in by_key:
            ordered.append(by_key.pop(key))
    ordered.extend(by_key.values())
    return FieldSchema(schema_id="profile", name=getattr(profile, "profile_id", "") or "", fields=ordered)


def _legacy_field_set(profile: Any) -> FieldSchema | None:
    """Transitional: a profile persisted before its contract was embedded still
    resolves through the registry. Removed once every profile is migrated."""
    if not (getattr(profile, "field_overrides", None) or getattr(profile, "field_schema_id", None)):
        return None
    try:
        from polaris.fields.loader import resolve_merged_field_schema
    except ImportError:  # pragma: no cover - registry removed
        return None
    return resolve_merged_field_schema(profile)


def validate_fields(fields: Iterable[FieldDef | dict[str, Any]]) -> list[ContractIssue]:
    issues: list[ContractIssue] = []
    parsed: list[FieldDef] = []
    for raw in fields:
        try:
            parsed.append(_coerce_field(raw))
        except Exception as exc:
            issues.append(f"invalid field definition: {exc}")
    keys = [(f.scope, f.name) for f in parsed]
    for key, count in Counter(keys).items():
        if count > 1:
            issues.append(f"field '{key[1]}' is listed more than once for scope '{key[0].value}'")
    catalogue = catalogue_by_key()
    alias_keys = _compact_alias_keys()
    for field in parsed:
        if (field.scope, field.name) in catalogue:
            continue
        if not _CUSTOM_NAME.match(field.name):
            issues.append(
                f"custom field '{field.name}' must be lowercase letters, digits and underscores, "
                "starting with a letter"
            )
        if field.name in alias_keys:
            issues.append(f"custom field '{field.name}' clashes with an extraction alias; choose another name")
        same_name = [k for k in catalogue if k[1] == field.name]
        if same_name:
            base = catalogue[same_name[0]]
            if base.type != field.type or base.role != field.role:
                issues.append(
                    f"custom field '{field.name}' reuses a catalogue name with a different type or role"
                )
        if field.type == FieldType.ENUM and not field.enum_values:
            issues.append(f"enum field '{field.name}' requires enum_values")
    return issues


def _compact_alias_keys() -> set[str]:
    from polaris.extraction.compact_chunked import DOC_ALIAS_TO_FIELD, ROW_ALIAS_TO_FIELD

    return set(DOC_ALIAS_TO_FIELD) | set(ROW_ALIAS_TO_FIELD)


# ---------------------------------------------------------------------------
# Output columns
# ---------------------------------------------------------------------------


def _coerce_column(raw: OutputColumn | dict[str, Any]) -> OutputColumn:
    if isinstance(raw, OutputColumn):
        return raw
    if hasattr(raw, "model_dump"):
        raw = raw.model_dump()
    return OutputColumn.model_validate(raw)


def output_columns(profile: Any, model: Any = None) -> list[OutputColumn]:
    """Template columns when set, else the profile's, else none."""
    template = [_coerce_column(c) for c in (getattr(model, "output_columns", None) or [])]
    if template:
        return template
    own = [_coerce_column(c) for c in (getattr(profile, "output_columns", None) or [])]
    if own:
        return own
    if profile is not None:
        legacy = _legacy_output_columns(profile)
        if legacy:
            return legacy
    return []


def _legacy_output_columns(profile: Any) -> list[OutputColumn]:
    """Transitional: resolve a not-yet-embedded profile through the registry."""
    if not getattr(profile, "output_spec_id", None):
        return []
    try:
        from polaris.specs.loader import resolve_output_spec
    except ImportError:  # pragma: no cover - registry removed
        return []
    return [
        OutputColumn(
            header=c.header, source=c.source, fallback=c.fallback,
            transforms=list(c.transforms), width=c.width, number_format=c.number_format,
        )
        for c in resolve_output_spec(profile).columns
    ]


def _value_types(fields: FieldSchema) -> dict[str, str]:
    """Canonical path -> field type, so the writer can format custom columns."""
    out: dict[str, str] = {}
    for f in fields.fields:
        out[normalize_source_path(field_path(f))] = f.type.value
    return out


def columns_to_defs(
    columns: Iterable[OutputColumn | dict[str, Any]], fields: FieldSchema | None = None,
) -> list[ColumnDef]:
    """Adapt declarative columns to the ``ColumnDef`` list the row builder and
    writer iterate over. Paths are normalised so ``field.x``/``row.x`` and the
    legacy ``header.x``/``line_item.x`` spellings all resolve."""
    types = _value_types(fields) if fields is not None else {}
    defs: list[ColumnDef] = []
    for raw in columns:
        col = _coerce_column(raw)
        path = normalize_source_path(col.source)
        defs.append(ColumnDef(
            xlsx_header=col.header,
            canonical_path=path,
            width=col.width,
            number_format=col.number_format,
            fallback_path=normalize_source_path(col.fallback) if col.fallback else None,
            transforms=tuple(col.transforms or ()),
            value_type=types.get(path),
        ))
    return defs


def _explicit_distinct_billing_reference(profile: Any) -> bool:
    hints = getattr(profile, "line_item_hints", None)
    preference = getattr(hints, "billing_reference_preference", None)
    column_label = getattr(hints, "billing_reference_column_label", None)
    return (
        preference in {"none", "separate_column", "parent_identifier"}
        or (bool(column_label) and preference != "same_as_service_id")
    )


def _apply_billing_reference_rule(columns: list[ColumnDef], profile: Any) -> list[ColumnDef]:
    """A profile that declares a distinct billing reference must not have the
    reference column silently fall back to the service id."""
    if not _explicit_distinct_billing_reference(profile):
        return columns
    out: list[ColumnDef] = []
    for col in columns:
        if (
            col.canonical_path == "line_item.billing_reference"
            and col.fallback_path == "line_item.service_id"
        ):
            col = ColumnDef(
                xlsx_header=col.xlsx_header, canonical_path=col.canonical_path, width=col.width,
                number_format=col.number_format, fallback_path=None, transforms=col.transforms,
                value_type=col.value_type,
            )
        out.append(col)
    return out


def delivery_columns(profile: Any, model: Any = None) -> list[ColumnDef]:
    """The columns an invoice under ``profile`` (and optionally a template
    ``model``) is delivered with. Empty when nothing is configured."""
    columns = output_columns(profile, model)
    if not columns:
        return []
    defs = columns_to_defs(columns, field_set(profile) if profile is not None else default_field_set())
    return _apply_billing_reference_rule(defs, profile)


def _paths_in(fields: FieldSchema) -> dict[str, FieldDef]:
    return {field_path(f): f for f in fields.fields}


def _canonical_to_contract_path(path: str) -> str:
    """Accept legacy ``header.x``/``line_item.x`` and bare totals as ``field.x``/``row.x``."""
    if path.startswith("header."):
        return "field." + path.removeprefix("header.")
    if path.startswith("line_item."):
        return "row." + path.removeprefix("line_item.")
    if path.startswith(("field.", "row.", "computed.")):
        return path
    return "field." + path


def validate_output_columns(
    columns: Iterable[OutputColumn | dict[str, Any]], fields: FieldSchema,
) -> list[ContractIssue]:
    issues: list[ContractIssue] = []
    parsed: list[OutputColumn] = []
    for raw in columns:
        try:
            parsed.append(_coerce_column(raw))
        except Exception as exc:
            issues.append(f"invalid output column: {exc}")
    headers = [c.header.strip() for c in parsed]
    if any(not h for h in headers):
        issues.append("every column requires a non-empty header")
    duplicates = sorted(h for h, n in Counter(headers).items() if h and n > 1)
    if duplicates:
        issues.append(f"column headers must be unique: {', '.join(duplicates)}")
    known = _paths_in(fields)
    for col in parsed:
        label = col.header.strip() or "(unnamed)"
        if not col.source.strip():
            issues.append(f"column '{label}' requires a source")
        if col.transforms and col.source.startswith("computed."):
            issues.append(f"column '{label}' cannot transform a computed value")
        for path in (col.source, col.fallback):
            if not path:
                continue
            contract_path = _canonical_to_contract_path(path)
            if contract_path.startswith("computed."):
                if contract_path not in COMPUTED_SOURCES:
                    issues.append(f"column '{label}' references unknown computed value '{path}'")
                continue
            if contract_path not in known:
                scope = "document" if contract_path.startswith("field.") else "row"
                name = contract_path.split(".", 1)[1]
                issues.append(f"column '{label}' references unknown {scope} field '{name}'")
    return list(dict.fromkeys(issues))


def date_format_issues(
    columns: Iterable[OutputColumn | dict[str, Any]], fields: FieldSchema,
) -> list[ContractIssue]:
    """Every delivered date must come with the printed format the supplier
    uses, or day/month ambiguity silently corrupts the deliverable."""
    known = _paths_in(fields)
    issues: list[ContractIssue] = []
    for raw in columns:
        col = _coerce_column(raw)
        for path in (col.source, col.fallback):
            field = known.get(_canonical_to_contract_path(path)) if path else None
            if field is not None and field.type == FieldType.DATE and not field.date_format:
                issues.append(f"Mapped date field '{path}' requires an explicit printed date format.")
    return list(dict.fromkeys(issues))


def readiness_issues(profile: Any, *, for_status: str | None = None) -> list[ContractIssue]:
    """Structural problems with a profile's contract, plus the stricter rules a
    training/active profile must satisfy (non-empty lists, date formats, an
    amount field to reconcile against)."""
    fields = field_set(profile)
    columns = output_columns(profile)
    issues = validate_fields(_profile_fields(profile))
    issues.extend(validate_output_columns(columns, fields))
    status = for_status or getattr(profile, "status", None)
    if status in ("training", "active"):
        if not _profile_fields(profile):
            issues.append("No fields to read are configured; add at least one field")
        if not columns:
            issues.append("No output columns are configured; add at least one delivered column")
        issues.extend(date_format_issues(columns, fields))
        if not any(f.scope == FieldScope.ROW and f.role == FieldRole.AMOUNT for f in fields.fields):
            issues.append("At least one row field with the amount role is required")
    return list(dict.fromkeys(issues))


def suggest_columns_from_headers(headers: Iterable[str]) -> list[OutputColumn]:
    """Blueprint headers as unmapped columns (empty source) for review."""
    out: list[OutputColumn] = []
    seen: set[str] = set()
    for header in headers:
        text = str(header or "").strip()
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        out.append(OutputColumn(header=text, source=""))
    return out


# ---------------------------------------------------------------------------
# Raw extraction workbook (no profile)
# ---------------------------------------------------------------------------

_RAW_HIDDEN = {"output_type", "confidence", "source_page", "source_row_id", "line_number"}


def raw_workbook_columns(invoice: Any) -> list[ColumnDef]:
    """One column per extracted row field, headers being the field names, in
    catalogue order then any custom field. This is the Line items sheet of the
    raw extraction workbook; it is a dump of what was read, not a deliverable."""
    names: list[str] = []
    seen: set[str] = set()
    present: set[str] = set()
    for row in getattr(invoice, "rows", None) or []:
        present.update(k for k, v in row.items() if v is not None and not str(k).startswith("_"))
    for base in CANONICAL_FIELDS:
        if base.scope == FieldScope.ROW and base.name in present and base.name not in seen:
            names.append(base.name)
            seen.add(base.name)
    for name in sorted(present):
        if name not in seen:
            names.append(name)
            seen.add(name)
    types = {f.name: f.type.value for f in CANONICAL_FIELDS if f.scope == FieldScope.ROW}
    return [
        ColumnDef(xlsx_header=name, canonical_path=f"line_item.{name}", value_type=types.get(name))
        for name in names
        if name not in _RAW_HIDDEN
    ]


def raw_document_fields(invoice: Any) -> list[tuple[str, Any]]:
    """Every extracted document field as (name, value), for the Invoice sheet."""
    fields = getattr(invoice, "fields", None) or {}
    ordered: list[tuple[str, Any]] = []
    seen: set[str] = set()
    def _blank(value: Any) -> bool:
        return value is None or (isinstance(value, list | dict | str) and not value)

    for base in CANONICAL_FIELDS:
        if base.scope == FieldScope.DOCUMENT and base.name in fields and base.name not in _RAW_HIDDEN:
            seen.add(base.name)
            if not _blank(fields[base.name]):
                ordered.append((base.name, fields[base.name]))
    for name in sorted(fields):
        if name in seen or name in _RAW_HIDDEN or str(name).startswith("_") or _blank(fields[name]):
            continue
        ordered.append((name, fields[name]))
    return ordered
