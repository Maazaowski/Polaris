"""AI-assisted SupplierProfile authoring.

This is the profile-level analogue of ``polaris.models.authoring`` (which
authors the declarative *ExtractionModel*). Here the AI authors the upstream
*SupplierProfile* config: identity, the fields to read (catalogue picks with
printed-label hints, plus custom fields), the delivered columns, the
deterministic grouped-line-item policy, fingerprint tuning, and notes, from a
handful of sample invoices plus the user's chat guidance.

It makes ONE AI call per invocation and returns a draft profile (the authorable
subset) plus a natural-language assistant message. The interactive loop
(upload -> chat -> preview -> refine) is orchestrated by the Celery task in
``polaris.tasks.worker`` and the API in ``polaris.api.profile_authoring``.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation

import structlog

from polaris import runtime_settings
from polaris.ai_debug import traced_chat_completion
from polaris.config import settings
from polaris.fields.catalogue import COMPUTED_SOURCES, catalogue_by_key, default_field_set, field_path
from polaris.fields.schema import FieldDef, FieldRole, FieldSchema, FieldScope, FieldType
from polaris.llm import get_ai_client
from polaris.output.columns import TRANSFORMS, OutputColumn

logger = structlog.get_logger()

# Allowed enum values for the authorable line-item policy. Kept in lockstep with
# extraction/normalization.py (GROUPING_GRANULARITIES / GROUPING_ID_PREFS) and the
# LineItemHints field docstrings so the model cannot invent unsupported values.
_GRANULARITIES = ["per_charge_row", "per_service_group", "per_total_group"]
_SERVICE_ID_PREFS = [
    "first_identifier", "parent_identifier", "total_row_identifier", "leftmost_identifier",
    "child_identifier",
]
_BILLING_REF_PREFS = ["same_as_service_id", "parent_identifier", "separate_column", "none"]
_AMOUNT_SOURCES = ["group_total", "first_amount", "label_amount", "label_amount_minus_tax", "table_charges_column"]
_TAX_SOURCES = ["none", "label_amount", "group_total_minus_amount", "table_tax_column"]
_TAX_OUTPUT_MODES = ["auto", "extract_exact", "calculate", "none"]
_TAX_RATE_SOURCES = ["auto", "invoice_tax_rate", "invoice_tax_divided_by_subtotal", "consistent_line_tax_rate"]
_COMPUTED_OUTPUT_SOURCES = list(COMPUTED_SOURCES)
_OUTPUT_TRANSFORMS = list(TRANSFORMS)
_FIELD_TYPES = [t.value for t in FieldType]
_FIELD_ROLES = [r.value for r in FieldRole]

PROFILE_AUTHORING_SYSTEM_PROMPT = """You are an extraction-onboarding assistant for Polaris.

You configure a SupplierProfile: a small JSON config that tells the system how to
read ONE supplier's invoice layout and which columns to deliver for it.
You are given, for each sample invoice: the coordinate-aware PDF text and a
baseline AI extraction. The baseline is evidence, not guaranteed ground truth.
You may also be given the user's guidance, an XLS/XLSX blueprint per invoice,
and the diff between the current draft's preview and that blueprint.

Your job each turn:
1. Read the layouts and the user's guidance.
2. Build an internal extraction plan before choosing profile fields. The plan
   must decide supplier/document type, which fields to read, the delivered
   columns, header labels, invoice totals, line-item section boundaries, row
   granularity, service ID source, billing reference source, amount source, tax
   source, page-break carry-forward rules, skip rules, reconciliation targets,
   and unresolved risks.
3. Produce the BEST SupplierProfile draft you can, conforming exactly to the
   provided JSON schema. Only set fields you have real evidence for; leave the
   rest at their defaults (empty string / empty list / null).
4. Write a short, plain-language assistant_message explaining the extraction
   plan decisions you encoded in the draft, what changed, and why. Describe every
   delivered column by header, source, fallback, and reason. Ask one focused
   question when the evidence is ambiguous.

Guidance on the load-bearing fields:
- identity.canonical_name + aliases: the supplier's name and the variants printed
  on documents.
- fields: the COMPLETE list of fields to read from this supplier's invoices, every
  turn. Pick from the field catalogue by name and scope (document or row); the
  catalogue fixes each pick's type and role, you supply the printed label_hint and,
  for dates, the explicitly printed input format such as %d/%m/%Y in date_format
  (delivery is normalized to %m/%d/%Y). A name that is not in the catalogue is a
  custom field: give it a scope, type and role. Never relabel invoice_date as
  "Billing Period Start" to simulate delivery; add billing_period_start instead.
- output_columns: the COMPLETE ordered list of delivered columns, every turn.
  With a blueprint, its headers ARE the contract: deliver exactly those headers in
  that order and map each to the field whose values match the blueprint. Without
  a blueprint, propose the columns the invoice evidence supports (identifiers,
  dates, amounts, tax) and say so. A field.* source repeats one document value;
  a row.* source resolves separately for every delivered line; computed.line_tax
  is the per-line tax the system derives.
- transforms are safe delivery normalizations applied after source/fallback.
  Use digits_only for requests such as "remove dashes from account number";
  never claim a requested transform is implemented only by mentioning it in notes.
- Only map a column to an alternative field when the user explicitly requests it
  or blueprint values consistently match that field across samples. Mixed or weak
  evidence requires an open question and no speculative mapping.
- Preserve existing fields and columns unless the user requests a change or
  strong new evidence contradicts them. Omitting a column removes it.
- line_item_hints.line_item_granularity: per_charge_row (one row per charge),
  per_service_group, or per_total_group (one row per service/total block).
- service_id_preference / billing_reference_preference: which printed identifier
  becomes the delivered service id and billing reference.
- When customer identifiers, supplier-internal references, account/sub-account
  numbers, or invoice numbers share the same shape, never use an unqualified
  broad regex. Encode the printed label/context that distinguishes the customer
  identifier or ask one focused question.
- *_column_label: the printed column header for the service id, billing reference,
  amount, or tax amount.
- amount_source / tax_source / tax_output_mode / tax_rate_source: executable
  amount and tax policies used when the blueprint shows how amounts and taxes
  should be delivered.
- detail_start_marker: the text where the line-item section begins.
- skip_row_keywords: text on rows that must NOT become line items (e.g. running totals).
- notes: free-text guidance for the AI extractor about this layout.

Use the available extraction toolkit: classify the document, read header fields,
fingerprint layout anchors, learn from XLS/XLSX blueprint rows, plan extraction
strategy, preserve parent-child blocks across pages, resolve grouped rows,
choose tax behavior, reconcile against invoice totals, diff against the
blueprint, explain differences, and route unresolved risks to review.

Use attached XLS/XLSX rows as the delivery contract for columns, row structure,
and mapping semantics. Use the PDF as evidence for printed facts and totals. A
difference is evidence to investigate, not proof that either side is wrong. Do
not drop invoice-backed charges only because they are absent from the blueprint;
explain exclusions or unresolved differences. Use the blueprint to learn what to
deliver and the PDF to prove what was printed. Explain every meaningful difference.

When discovery_candidates is present, select only a supplied candidate_id. Set
selected_plan_id to null when the deterministic evidence is insufficient and
state the exact ambiguity; never invent executable formulas or regexes."""


@dataclass
class InvoiceEvidence:
    """Per-invoice grounding for one authoring call."""

    label: str
    page_texts: list[str]
    target: dict  # _build_target-style baseline extraction evidence
    expected_rows: list[list[str]] | None = None  # parsed expected deliverable, if uploaded
    blueprint_context: dict | None = None  # parsed blueprint headers/rows/totals/warnings, if uploaded
    diff_feedback: str | None = None  # current draft's preview vs expected, if available


@dataclass
class ProfileAuthoringResult:
    draft: dict  # the authorable SupplierProfile subset
    assistant_message: str
    open_questions: list[str] = field(default_factory=list)
    confidence: float = 0.0
    ai_model_name: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    duration_ms: int = 0
    selected_plan_id: str | None = None


def _field_path(field) -> str:
    return field_path(field)


def available_output_source_paths(field_set: FieldSchema) -> list[str]:
    return [*[_field_path(f) for f in field_set.fields], *_COMPUTED_OUTPUT_SOURCES]


def authoring_field_set(*extra: FieldSchema | list | None) -> FieldSchema:
    """The field vocabulary one authoring turn may map to: the whole catalogue
    plus every custom field already present in ``extra`` (a source profile's
    field set, the current draft's fields, ...)."""
    fields = list(default_field_set().fields)
    known = {(f.scope, f.name) for f in fields}
    for item in extra:
        if item is None:
            continue
        entries = item.fields if isinstance(item, FieldSchema) else item
        for raw in entries:
            fdef = raw if isinstance(raw, FieldDef) else _draft_entry_to_field(raw)
            if fdef is None or (fdef.scope, fdef.name) in known:
                continue
            fields.append(fdef)
            known.add((fdef.scope, fdef.name))
    return FieldSchema(schema_id="authoring", name="Authoring", fields=fields)


def _field_item_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "scope": {"type": "string", "enum": ["document", "row"]},
            "type": {"type": ["string", "null"], "enum": [*_FIELD_TYPES, None]},
            "role": {"type": ["string", "null"], "enum": [*_FIELD_ROLES, None]},
            "label_hint": {"type": ["string", "null"]},
            "date_format": {"type": ["string", "null"]},
            "required": {"type": "boolean"},
            "description": {"type": ["string", "null"]},
        },
        "required": ["name", "scope", "type", "role", "label_hint", "date_format", "required", "description"],
        "additionalProperties": False,
    }


def _output_column_schema(source_paths: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "header": {"type": "string"},
            "source": {"type": "string", "enum": source_paths},
            "fallback": {"type": ["string", "null"], "enum": [*source_paths, None]},
            "transforms": {
                "type": "array",
                "items": {"type": "string", "enum": _OUTPUT_TRANSFORMS},
            },
            "number_format": {"type": ["string", "null"]},
            "width": {"type": ["integer", "null"]},
            "reason": {"type": "string"},
        },
        "required": ["header", "source", "fallback", "transforms", "number_format", "width", "reason"],
        "additionalProperties": False,
    }


def build_profile_authoring_schema(field_set: FieldSchema) -> dict:
    """Strict JSON schema for the authorable subset of a SupplierProfile.

    Column sources are pinned to ``field_set`` (the catalogue plus the custom
    fields already in play) so the model cannot invent a source path. A custom
    field it adds this turn becomes mappable on the next one.
    """
    source_paths = list(dict.fromkeys(available_output_source_paths(field_set)))
    return {
        "name": "supplier_profile_draft",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "assistant_message": {"type": "string"},
                "open_questions": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "number"},
                "selected_plan_id": {
                    "type": ["string", "null"],
                    "enum": ["deterministic.v1", None],
                },
                "profile": {
                    "type": "object",
                    "properties": {
                        "canonical_name": {"type": "string"},
                        "aliases": {"type": "array", "items": {"type": "string"}},
                        "output_type": {"type": "string"},
                        "notes": {"type": ["string", "null"]},
                        "fields": {"type": "array", "items": _field_item_schema()},
                        "output_columns": {"type": "array", "items": _output_column_schema(source_paths)},
                        "detail_start_marker": {"type": ["string", "null"]},
                        "detail_end_marker": {"type": ["string", "null"]},
                        "line_item_granularity": {"type": ["string", "null"], "enum": [*_GRANULARITIES, None]},
                        "service_id_preference": {"type": ["string", "null"], "enum": [*_SERVICE_ID_PREFS, None]},
                        "billing_reference_preference": {
                            "type": ["string", "null"], "enum": [*_BILLING_REF_PREFS, None]},
                        "service_id_column_label": {"type": ["string", "null"]},
                        "billing_reference_column_label": {"type": ["string", "null"]},
                        "amount_column_label": {"type": ["string", "null"]},
                        "tax_amount_column_label": {"type": ["string", "null"]},
                        "amount_source": {"type": ["string", "null"], "enum": [*_AMOUNT_SOURCES, None]},
                        "tax_source": {"type": ["string", "null"], "enum": [*_TAX_SOURCES, None]},
                        "tax_output_mode": {"type": ["string", "null"], "enum": [*_TAX_OUTPUT_MODES, None]},
                        "tax_rate_source": {"type": ["string", "null"], "enum": [*_TAX_RATE_SOURCES, None]},
                        "service_id_value_pattern": {"type": ["string", "null"]},
                        "billing_reference_value_pattern": {"type": ["string", "null"]},
                        "detail_table_anchors": {"type": "array", "items": {"type": "string"}},
                        "table_column_labels": {"type": "array", "items": {"type": "string"}},
                        "subtotal_keywords": {"type": "array", "items": {"type": "string"}},
                        "tax_keywords": {"type": "array", "items": {"type": "string"}},
                        "skip_row_keywords": {"type": "array", "items": {"type": "string"}},
                        "include_zero_amount_line_items": {"type": "boolean"},
                        "require_line_item_identifier": {"type": "boolean"},
                    },
                    "required": [
                        "canonical_name", "aliases", "output_type", "notes", "fields", "output_columns",
                        "detail_start_marker", "detail_end_marker", "line_item_granularity",
                        "service_id_preference", "billing_reference_preference",
                        "service_id_column_label", "billing_reference_column_label",
                        "amount_column_label", "tax_amount_column_label", "amount_source",
                        "tax_source", "tax_output_mode", "tax_rate_source",
                        "service_id_value_pattern", "billing_reference_value_pattern",
                        "detail_table_anchors", "table_column_labels", "subtotal_keywords",
                        "tax_keywords", "skip_row_keywords", "include_zero_amount_line_items",
                        "require_line_item_identifier",
                    ],
                    "additionalProperties": False,
                },
            },
            "required": [
                "assistant_message", "open_questions", "confidence", "selected_plan_id", "profile",
            ],
            "additionalProperties": False,
        },
    }


def _draft_entry_to_field(entry: dict) -> FieldDef | None:
    """One authored ``fields`` entry (or a legacy ``field_path`` entry) as a
    FieldDef: catalogue picks take type/role from the catalogue and keep only
    the hints; anything else is a custom field taken as written."""
    if not isinstance(entry, dict):
        return None
    name = str(entry.get("name") or "").strip()
    scope = entry.get("scope")
    path = entry.get("field_path")
    if path and not name:
        prefix, _, name = str(path).partition(".")
        scope = "document" if prefix in ("field", "header") else "row"
    if not name:
        return None
    try:
        scope_val = FieldScope(str(scope or "document"))
    except ValueError:
        scope_val = FieldScope.DOCUMENT
    base = catalogue_by_key().get((scope_val, name))
    if base is None:
        same_name = [k for k in catalogue_by_key() if k[1] == name]
        if len(same_name) == 1 and not scope:
            scope_val = same_name[0][0]
            base = catalogue_by_key()[same_name[0]]
    label_hint = entry.get("label_hint") or None
    date_format = entry.get("date_format") or None
    required = bool(entry.get("required", False))
    if base is not None:
        return FieldDef(
            name=name, scope=scope_val, type=base.type, role=base.role,
            label_hint=label_hint, date_format=date_format, required=required or base.required,
            enum_values=list(base.enum_values), description=entry.get("description") or "",
        )
    try:
        ftype = FieldType(str(entry.get("type") or "string"))
    except ValueError:
        ftype = FieldType.STRING
    try:
        role = FieldRole(str(entry.get("role") or "none"))
    except ValueError:
        role = FieldRole.NONE
    return FieldDef(
        name=name, scope=scope_val, type=ftype, role=role, label_hint=label_hint,
        date_format=date_format, required=required, enum_values=list(entry.get("enum_values") or []),
        description=entry.get("description") or "",
    )


def _field_to_profile_entry(fdef: FieldDef) -> dict:
    base = catalogue_by_key().get((fdef.scope, fdef.name))
    entry = {
        "name": fdef.name,
        "scope": fdef.scope.value,
        "type": fdef.type.value,
        "role": fdef.role.value,
        "label_hint": fdef.label_hint,
        "date_format": fdef.date_format,
        "required": bool(fdef.required),
    }
    if base is None:
        entry["enum_values"] = list(fdef.enum_values)
        entry["description"] = fdef.description or ""
    elif fdef.description and fdef.description != base.description:
        entry["description"] = fdef.description
    return entry


def _draft_column_to_profile_entry(entry: dict) -> dict | None:
    header = str(entry.get("header") or "").strip()
    if not header:
        return None
    column = OutputColumn(
        header=header,
        source=str(entry.get("source") or "").strip(),
        fallback=(str(entry.get("fallback")).strip() or None) if entry.get("fallback") else None,
        transforms=list(entry.get("transforms") or []),
        width=int(entry.get("width") or 15),
        number_format=entry.get("number_format") or None,
    )
    return column.model_dump(mode="json")


def draft_to_supplier_profile_dict(draft: dict, *, field_set: FieldSchema | None = None) -> dict:
    """Map the flat authored ``draft`` onto the SupplierProfile JSON shape.

    Returns a dict that ``SupplierProfile.model_validate`` accepts. ``profile_id``
    and ``delivery`` are intentionally left for the user to set at finalize time.
    ``fields`` / ``output_columns`` are written only when the draft carries them,
    so an edit session that omits them keeps the source profile's. Structural
    validity (sources resolve, headers unique) is checked at finalize time, not
    here, so a preview can always be rendered.
    """
    p = draft.get("profile", draft)
    result = {
        "identity": {
            "canonical_name": p.get("canonical_name") or "",
            "aliases": list(p.get("aliases") or []),
        },
        "classification": {"output_type": p.get("output_type") or "standard"},
        "notes": p.get("notes") or None,
        "advanced": {
            "document_structure": {
                "detail_start_marker": p.get("detail_start_marker") or None,
                "detail_end_marker": p.get("detail_end_marker") or None,
            },
            "line_item_hints": {
                "subtotal_keywords": list(p.get("subtotal_keywords") or []) or ["Subtotal", "Sub Total", "Sub-Total"],
                "tax_keywords": list(p.get("tax_keywords") or []) or ["Tax", "Taxes", "VAT"],
                "detail_table_anchors": list(p.get("detail_table_anchors") or []),
                "line_item_granularity": p.get("line_item_granularity") or None,
                "service_id_preference": p.get("service_id_preference") or None,
                "billing_reference_preference": p.get("billing_reference_preference") or None,
                "service_id_column_label": p.get("service_id_column_label") or None,
                "billing_reference_column_label": p.get("billing_reference_column_label") or None,
                "amount_column_label": p.get("amount_column_label") or None,
                "tax_amount_column_label": p.get("tax_amount_column_label") or None,
                "amount_source": p.get("amount_source") or None,
                "tax_source": p.get("tax_source") or None,
                "tax_output_mode": p.get("tax_output_mode") or None,
                "tax_rate_source": p.get("tax_rate_source") or None,
                "service_id_value_pattern": p.get("service_id_value_pattern") or None,
                "billing_reference_value_pattern": p.get("billing_reference_value_pattern") or None,
                "skip_row_keywords": list(p.get("skip_row_keywords") or []),
                "table_column_labels": list(p.get("table_column_labels") or []),
            },
            "include_zero_amount_line_items": bool(p.get("include_zero_amount_line_items")),
            "require_line_item_identifier": bool(p.get("require_line_item_identifier")),
            "extraction_plan": p.get("extraction_plan"),
        },
        "authoring_evidence": p.get("authoring_evidence"),
    }
    if "fields" in p:
        by_key: dict[tuple[FieldScope, str], FieldDef] = {}
        for entry in p.get("fields") or []:
            fdef = _draft_entry_to_field(entry)
            if fdef is not None:
                by_key[(fdef.scope, fdef.name)] = fdef
        result["fields"] = [_field_to_profile_entry(f) for f in by_key.values()]
    if "output_columns" in p:
        columns: list[dict] = []
        seen: set[str] = set()
        for entry in p.get("output_columns") or []:
            column = _draft_column_to_profile_entry(entry)
            if column is None or column["header"] in seen:
                continue
            seen.add(column["header"])
            columns.append(column)
        result["output_columns"] = columns
    return result


def supplier_profile_to_draft(profile) -> dict:
    """Inverse of ``draft_to_supplier_profile_dict``: seed an authoring draft from an
    existing profile so the assistant can refine its extraction hints.

    Only the AI-authorable surface is reflected (identity, classification, fields,
    output columns, and the advanced hint block). Delivery, training, fingerprint,
    and lifecycle stay on the source profile and are re-merged at finalize time.
    """
    ds = profile.document_structure
    lih = profile.line_item_hints
    advanced = profile.advanced
    return {
        "profile": {
            "canonical_name": profile.identity.canonical_name,
            "aliases": list(profile.identity.aliases or []),
            "output_type": profile.classification.output_type,
            "fields": [
                {
                    "name": f.name,
                    "scope": f.scope.value,
                    "type": f.type.value,
                    "role": f.role.value,
                    "label_hint": f.label_hint,
                    "date_format": f.date_format,
                    "required": bool(f.required),
                    "description": f.description or None,
                }
                for f in (profile.fields or [])
            ],
            "output_columns": [
                {
                    "header": c.header,
                    "source": c.source,
                    "fallback": c.fallback,
                    "transforms": list(c.transforms),
                    "number_format": c.number_format,
                    "width": c.width,
                    "reason": "Existing profile column.",
                }
                for c in (profile.output_columns or [])
            ],
            "notes": profile.notes,
            "detail_start_marker": ds.detail_start_marker,
            "detail_end_marker": ds.detail_end_marker,
            "subtotal_keywords": list(lih.subtotal_keywords or []),
            "tax_keywords": list(lih.tax_keywords or []),
            "detail_table_anchors": list(lih.detail_table_anchors or []),
            "line_item_granularity": lih.line_item_granularity,
            "service_id_preference": lih.service_id_preference,
            "billing_reference_preference": lih.billing_reference_preference,
            "service_id_column_label": lih.service_id_column_label,
            "billing_reference_column_label": lih.billing_reference_column_label,
            "amount_column_label": lih.amount_column_label,
            "tax_amount_column_label": lih.tax_amount_column_label,
            "amount_source": lih.amount_source,
            "tax_source": lih.tax_source,
            "tax_output_mode": lih.tax_output_mode,
            "tax_rate_source": lih.tax_rate_source,
            "service_id_value_pattern": lih.service_id_value_pattern,
            "billing_reference_value_pattern": lih.billing_reference_value_pattern,
            "skip_row_keywords": list(lih.skip_row_keywords or []),
            "table_column_labels": list(lih.table_column_labels or []),
            "include_zero_amount_line_items": advanced.include_zero_amount_line_items,
            "require_line_item_identifier": advanced.require_line_item_identifier,
        }
    }


def merge_source_profile_config(source, authored: dict) -> dict:
    """Layer authored settings over a source profile without losing non-AI config.

    Fields merge by (scope, name) with the authored entry winning. Output
    columns are a complete list when present: an authored list (even empty)
    replaces the source's; a payload that omits the key keeps them.
    """
    source_dict = source.model_dump(mode="json")
    merged = {**source_dict, **authored}
    merged["advanced"] = {
        **(source_dict.get("advanced") or {}),
        **(authored.get("advanced") or {}),
    }
    fields = {
        (item.get("scope"), item.get("name")): item
        for item in source_dict.get("fields") or []
    }
    for item in authored.get("fields") or []:
        key = (item.get("scope"), item.get("name"))
        fields[key] = {**fields.get(key, {}), **item}
    merged["fields"] = list(fields.values())
    if "output_columns" not in authored:
        merged["output_columns"] = source_dict.get("output_columns") or []
    return merged


def _estimate_tokens(text: str) -> int:
    return len(text) // 4  # ~4 chars/token, matches models/authoring.py heuristic


def _invoice_totals(target: dict) -> dict:
    totals = dict(target.get("totals") or {})
    line_items = target.get("line_items") or []
    amount_total = 0.0
    tax_total = 0.0
    for item in line_items:
        try:
            amount_total += float(item.get("amount") or 0)
        except (TypeError, ValueError):
            pass
        try:
            tax_total += float(item.get("tax_amount") or 0)
        except (TypeError, ValueError):
            pass
    totals["sampled_line_amount_total"] = f"{amount_total:.2f}"
    totals["sampled_line_tax_total"] = f"{tax_total:.2f}"
    totals["sampled_line_count"] = len(line_items)
    return totals


def _values_for_source(target: dict, source: str) -> list[object]:
    if source.startswith(("field.", "header.")):
        name = source.split(".", 1)[1]
        value = (target.get("header") or {}).get(name)
        return [] if value in (None, "") else [value]
    if source.startswith(("row.", "line_item.")):
        name = source.split(".", 1)[1]
        return [
            item.get(name)
            for item in (target.get("line_items") or [])
            if item.get(name) not in (None, "")
        ]
    value = (target.get("totals") or {}).get(source)
    return [] if value in (None, "") else [value]


def _normalized_source_values(values: list[object], source: str) -> set[str]:
    is_date = source.endswith(("_date", "_start", "_end"))
    return {
        _date_for_compare(value) if is_date else _clean_compare_text(value)
        for value in values
        if value not in (None, "")
    }


def _blueprint_vs_invoice_summary(
    blueprint_context: dict | None,
    target: dict,
    *,
    columns: list[OutputColumn] | None = None,
    field_set: FieldSchema | None = None,
) -> dict | None:
    if not blueprint_context:
        return None
    invoice_totals = target.get("totals") or {}
    blueprint_totals = blueprint_context.get("totals") or {}
    comparisons = []
    warnings = []
    if blueprint_totals.get("amount") and invoice_totals.get("subtotal"):
        comparisons.append({
            "blueprint": "amount",
            "invoice": "subtotal",
            "blueprint_value": blueprint_totals["amount"],
            "invoice_value": invoice_totals["subtotal"],
        })
        if _decimal_for_compare(blueprint_totals["amount"]) != _decimal_for_compare(invoice_totals["subtotal"]):
            warnings.append(
                "Blueprint amount total differs from the printed invoice subtotal; "
                "explain the delivery semantics or reconcile the difference."
            )
    if blueprint_totals.get("tax") and invoice_totals.get("tax"):
        comparisons.append({
            "blueprint": "tax",
            "invoice": "tax",
            "blueprint_value": blueprint_totals["tax"],
            "invoice_value": invoice_totals["tax"],
        })
        if _decimal_for_compare(blueprint_totals["tax"]) != _decimal_for_compare(invoice_totals["tax"]):
            warnings.append(
                "Blueprint tax total differs from the printed invoice tax total; "
                "explain the delivery semantics or reconcile the difference."
            )
    header = target.get("header") or {}
    invoice_number = _clean_compare_text(header.get("invoice_number"))
    blueprint_invoice_numbers = {
        _clean_compare_text(value)
        for value in _blueprint_column_values(
            blueprint_context,
            {"extinvoicenumber", "invoicenumber"},
        )
    }
    if invoice_number and blueprint_invoice_numbers and invoice_number not in blueprint_invoice_numbers:
        warnings.append(
            "Blueprint invoice number differs from the baseline header extraction; verify the intended output mapping."
        )
    invoice_date = _date_for_compare(header.get("invoice_date"))
    blueprint_dates = {
        _date_for_compare(value)
        for value in _blueprint_column_values(blueprint_context, {"extdate", "invoicedate", "date"})
    }
    blueprint_dates.discard("")
    if invoice_date and blueprint_dates and invoice_date not in blueprint_dates:
        warnings.append(
            "Blueprint date differs from the baseline invoice date; check billing-period "
            "or row-date fields before choosing an output mapping."
        )
    mapping_evidence = []
    if columns and field_set:
        source_paths = available_output_source_paths(field_set)
        for column in columns:
            blueprint_values = _blueprint_column_values(
                blueprint_context, {_normalized_header_token(column.header)})
            if not blueprint_values:
                continue
            blueprint_normalized = _normalized_source_values(blueprint_values, column.source)
            base_values = _values_for_source(target, column.source)
            base_normalized = _normalized_source_values(base_values, column.source)
            alternatives = []
            if blueprint_normalized and blueprint_normalized != base_normalized:
                for source in source_paths:
                    if source == column.source or source.startswith("computed."):
                        continue
                    candidate = _normalized_source_values(_values_for_source(target, source), source)
                    if candidate and candidate == blueprint_normalized:
                        alternatives.append(source)
            mapping_evidence.append({
                "output_header": column.header,
                "base_source": column.source,
                "blueprint_values": blueprint_values,
                "base_values": base_values,
                "base_matches": bool(blueprint_normalized and blueprint_normalized == base_normalized),
                "matching_alternative_sources": alternatives,
            })
    return {
        "blueprint_row_count": blueprint_context.get("row_count"),
        "invoice_line_item_count_in_prompt": len(target.get("line_items") or []),
        "blueprint_totals": blueprint_totals,
        "invoice_totals": invoice_totals,
        "comparisons": comparisons,
        "output_mapping_evidence": mapping_evidence,
        "warnings": warnings,
    }


def _blueprint_column_values(blueprint_context: dict, accepted_headers: set[str]) -> list[str]:
    headers = blueprint_context.get("aligned_headers") or blueprint_context.get("raw_headers") or []
    rows = blueprint_context.get("aligned_rows") or []
    indexes = [
        index
        for index, header in enumerate(headers)
        if _normalized_header_token(header) in accepted_headers
    ]
    values: list[str] = []
    for row in rows:
        for index in indexes:
            if index >= len(row):
                continue
            value = str(row[index] or "").strip()
            if value and value not in values:
                values.append(value)
    return values


def _normalized_header_token(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _clean_compare_text(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def _decimal_for_compare(value: object) -> Decimal | None:
    try:
        return Decimal(str(value).replace(",", "").strip()).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _date_for_compare(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return _clean_compare_text(text)


def _build_user_prompt(
    *,
    field_set: FieldSchema,
    columns: list[OutputColumn],
    invoices: list[InvoiceEvidence],
    conversation: list[dict],
    current_draft: dict | None,
    discovery_report: dict | None,
    budget: int,
) -> str:
    """Assemble the authoring prompt, trimming layout text if over the token budget."""
    catalogue = [
        {"path": _field_path(f), "type": str(f.type), "role": str(f.role), "required": bool(f.required),
         "description": f.description, "label_hint": f.label_hint, "date_format": f.date_format}
        for f in field_set.fields
    ]
    deliverable = [
        {"header": c.header, "source": c.source, "fallback": c.fallback, "transforms": list(c.transforms)}
        for c in columns
    ]
    history = [
        {"role": m.get("role"), "content": m.get("content")}
        for m in conversation
        if m.get("role") in {"user", "assistant"}
    ]

    def assemble(page_text_chars: int | None) -> str:
        invoice_blocks = []
        for inv in invoices:
            texts = inv.page_texts
            if page_text_chars is not None:
                texts = [t[:page_text_chars] for t in texts]
            block = {
                "label": inv.label,
                "baseline_extracted_evidence": inv.target,
                "invoice_totals": _invoice_totals(inv.target),
                "layout_text": texts,
            }
            if inv.blueprint_context is not None:
                block["blueprint_context"] = inv.blueprint_context
                block["blueprint_vs_invoice_summary"] = _blueprint_vs_invoice_summary(
                    inv.blueprint_context, inv.target,
                    columns=columns, field_set=field_set)
            elif inv.expected_rows is not None:
                block["blueprint_context"] = {
                    "aligned_rows": inv.expected_rows,
                    "row_count": len(inv.expected_rows),
                    "sample_rows": inv.expected_rows[:10],
                }
                block["blueprint_vs_invoice_summary"] = _blueprint_vs_invoice_summary(
                    block["blueprint_context"], inv.target,
                    columns=columns, field_set=field_set)
            if inv.diff_feedback:
                block["preview_vs_blueprint_diff"] = inv.diff_feedback
            invoice_blocks.append(block)
        payload = {
            "field_catalogue": catalogue,
            "current_output_columns": deliverable,
            "allowed_output_sources": available_output_source_paths(field_set),
            "conversation": history,
            "current_draft": current_draft,
            "discovery_candidates": (
                {
                    "candidate_id": "deterministic.v1",
                    **discovery_report,
                }
                if discovery_report else None
            ),
            "sample_invoices": invoice_blocks,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    prompt = assemble(None)
    if _estimate_tokens(prompt) <= budget:
        return prompt
    # Progressively trim layout text per page until under budget (extracted evidence +
    # blueprint context + diffs are never trimmed - they are the grounding signal).
    for cap in (6000, 4000, 2500, 1500, 800):
        prompt = assemble(cap)
        if _estimate_tokens(prompt) <= budget:
            logger.info("profile_authoring.prompt_trimmed", page_text_chars=cap)
            return prompt
    raise ValueError(
        f"Profile authoring evidence exceeds the {budget:,}-token safeguard after compaction"
    )


def author_profile(
    *,
    field_set: FieldSchema,
    columns: list[OutputColumn],
    invoices: list[InvoiceEvidence],
    conversation: list[dict],
    current_draft: dict | None = None,
    discovery_report: dict | None = None,
) -> ProfileAuthoringResult:
    """One AI call: author a SupplierProfile draft grounded in the sample invoices.

    ``field_set`` is the vocabulary the draft may read and map (the catalogue
    plus custom fields already in play); ``columns`` are the columns currently
    configured, if any. ``conversation`` is the prior chat history (the latest
    user message included); ``current_draft`` is the previous turn's authored
    profile (the flat draft), so refinement turns build on what's there instead
    of starting over.
    """
    if not invoices:
        raise ValueError("profile authoring requires at least one extracted invoice")

    schema = build_profile_authoring_schema(field_set)
    user_prompt = _build_user_prompt(
        field_set=field_set,
        columns=columns,
        invoices=invoices,
        conversation=conversation,
        current_draft=current_draft,
        discovery_report=discovery_report,
        budget=min(
            settings.model_authoring_max_input_tokens,
            settings.profile_discovery_max_prompt_tokens,
        ),
    )

    client = get_ai_client(purpose="profile_authoring")
    model_name = runtime_settings.openai_model_model_generation()
    started = time.monotonic()
    response = traced_chat_completion(
        client,
        call_type="profile_authoring",
        context=invoices[0].label if invoices else "forge",
        model=model_name,
        messages=[
            {"role": "system", "content": PROFILE_AUTHORING_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_schema", "json_schema": schema},
        max_completion_tokens=runtime_settings.openai_max_output_tokens(),
    )
    duration_ms = int((time.monotonic() - started) * 1000)
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("profile authoring returned empty content")
    raw = json.loads(content)
    usage = response.usage
    return ProfileAuthoringResult(
        draft={"profile": raw["profile"]},
        assistant_message=raw.get("assistant_message", ""),
        open_questions=list(raw.get("open_questions") or []),
        confidence=float(raw.get("confidence") or 0.0),
        ai_model_name=model_name,
        tokens_input=(usage.prompt_tokens if usage else 0),
        tokens_output=(usage.completion_tokens if usage else 0),
        duration_ms=duration_ms,
        selected_plan_id=raw.get("selected_plan_id"),
    )
