"""Deliverable column mapping: resolves a column's source path against a canonical invoice."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from polaris.output.formatting import format_deliverable_date
from polaris.validation.schema import ExtractedDocument, LineItem

_BARE_TOTAL_FIELDS = frozenset({"subtotal", "tax", "fees", "total_due", "tax_rate", "current_charges"})


def normalize_source_path(path: str) -> str:
    """Map field./row. prefixes and legacy header./line_item. aliases to canonical paths."""
    if path.startswith("field."):
        name = path.removeprefix("field.")
        if name in _BARE_TOTAL_FIELDS:
            return name
        return f"header.{name}"
    if path.startswith("row."):
        return f"line_item.{path.removeprefix('row.')}"
    return path


@dataclass(frozen=True)
class ColumnDef:
    xlsx_header: str
    canonical_path: str
    width: int = 15
    number_format: str | None = None
    fallback_path: str | None = None
    transforms: tuple[str, ...] = ()
    # The field type behind ``canonical_path`` (string/date/number/currency/
    # integer/enum) when the contract knows it, so custom columns format
    # correctly without a hard-coded path list.
    value_type: str | None = None


def get_header_value(canonical_path: str, header: dict, invoice: dict) -> object:
    """Resolve a canonical_path to a value from the invoice data."""
    if canonical_path.startswith("header."):
        field = canonical_path.removeprefix("header.")
        value = header.get(field)
        if value is None:
            value = (invoice.get("fields") or {}).get(field)
        return value
    if canonical_path in ("subtotal", "tax", "fees", "total_due", "tax_rate"):
        return invoice.get(canonical_path)
    return None


def get_line_item_value(canonical_path: str, line_item: dict, header: dict,
                        invoice: dict, fallback_path: str | None = None) -> object:
    """Resolve a canonical_path to a value, checking line_item first then header/invoice.

    If the primary path returns None and a fallback_path is set, try the fallback.
    """
    if canonical_path.startswith("computed."):
        return None  # computed fields are handled by the writer

    canonical_path = normalize_source_path(canonical_path)
    if fallback_path:
        fallback_path = normalize_source_path(fallback_path)

    if canonical_path.startswith("line_item."):
        field = canonical_path.removeprefix("line_item.")
        value = line_item.get(field)
        if value is None and fallback_path:
            value = get_line_item_value(fallback_path, line_item, header, invoice)
        return value

    value = get_header_value(canonical_path, header, invoice)
    if value is None and fallback_path:
        value = get_line_item_value(fallback_path, line_item, header, invoice)
    return value


def resolve_output_cell(
    canonical_path: str,
    line_item: LineItem,
    invoice: ExtractedDocument,
    *,
    fallback_path: str | None = None,
) -> object:
    """Resolve a column path from typed extracted models (avoids JSON Decimal→str)."""
    canonical_path = normalize_source_path(canonical_path)
    if fallback_path:
        fallback_path = normalize_source_path(fallback_path)
    if canonical_path.startswith("computed."):
        return None

    if canonical_path.startswith("line_item."):
        field = canonical_path.removeprefix("line_item.")
        value = getattr(line_item, field, None)
        if value is None and fallback_path:
            value = resolve_output_cell(fallback_path, line_item, invoice)
        return value

    if canonical_path.startswith("header."):
        field = canonical_path.removeprefix("header.")
        value = getattr(invoice.header, field, None)
        if value is None:
            # A custom document field lives only in ``invoice.fields``.
            value = (invoice.fields or {}).get(field)
        if value is None and fallback_path:
            value = resolve_output_cell(fallback_path, line_item, invoice)
        return value

    if canonical_path in ("subtotal", "tax", "fees", "total_due", "tax_rate"):
        value = getattr(invoice, canonical_path, None)
        if value is None and fallback_path:
            value = resolve_output_cell(fallback_path, line_item, invoice)
        return value

    return None


_NUMERIC_OUTPUT_PATHS = frozenset({
    "line_item.amount",
    "line_item.quantity",
    "line_item.unit_rate",
    "line_item.plan_cost",
    "line_item.equipment_cost",
    "computed.line_tax",
})


def normalize_output_value(value: object, canonical_path: str, value_type: str | None = None) -> object:
    """Normalize a deliverable cell value for comparison and XLSX output.

    Amounts and tax are coerced to float (2 dp for tax, flexible for amount).
    Dates become MM/DD/YYYY strings. Prevents 850 vs 850.00 false mismatches.
    ``value_type`` (from the profile's field set) decides for paths this module
    does not know, i.e. custom fields.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return format_deliverable_date(value)
    if isinstance(value, date):
        return format_deliverable_date(value)
    if (
        value_type == "date"
        or canonical_path.endswith("_date")
        or canonical_path.endswith(".invoice_date")
        or canonical_path.endswith(".due_date")
        or canonical_path.endswith(".billing_period_start")
        or canonical_path.endswith(".billing_period_end")
    ):
        return format_deliverable_date(value)
    if (
        canonical_path in _NUMERIC_OUTPUT_PATHS
        or canonical_path == "computed.line_tax"
        or value_type in ("number", "currency")
    ):
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return value
        if canonical_path == "computed.line_tax":
            return round(float(number), 2)
        # Amount: use float so XLSX stores a number, not text
        return round(float(number), 2)
    return value


def apply_output_transforms(value: object, transforms: tuple[str, ...] | list[str]) -> object:
    """Apply the small, deterministic transform allowlist used by profile mappings."""
    if value is None or not transforms:
        return value
    result = str(value)
    for transform in transforms:
        if transform == "digits_only":
            result = "".join(char for char in result if char.isdigit())
        elif transform == "trim":
            result = result.strip()
        elif transform == "uppercase":
            result = result.upper()
        elif transform == "lowercase":
            result = result.lower()
    return result
