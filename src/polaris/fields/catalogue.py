"""The catalogue of canonical invoice fields the pipeline knows how to read.

Reconciliation, coercion, the compact extractor's JSON schema and the template
interpreter all depend on a fixed understanding of what an invoice field *is*
(its scope, type and role). That knowledge lives here, read-only. A supplier
profile *selects* from this catalogue (``SupplierProfile.fields``) and sets
per-supplier hints on each pick (printed label, date format, required); it may
also add custom fields the catalogue does not know.

Nothing in this module is a deliverable: the output columns a supplier ships
are configured on the profile (or on a template) and start empty.
"""

from __future__ import annotations

from polaris.fields.schema import FieldDef, FieldRole, FieldSchema, FieldScope, FieldType

CHARGE_TYPE_VALUES = [
    "recurring", "one_time", "tax", "fee", "credit",
    "adjustment", "surcharge", "usage", "unknown",
]

# Parity with models/authoring.py static enums.
AUTHORING_HEADER_FIELD_NAMES = [
    "invoice_number", "invoice_date", "due_date", "account_number", "ban",
    "billing_period_start", "billing_period_end", "currency", "po_number",
]
AUTHORING_ITEM_FIELD_NAMES = [
    "service_id", "billing_reference", "description", "charge_type",
    "amount", "tax_amount", "currency", "billing_period_start",
    "billing_period_end", "quantity", "unit_rate",
]
AUTHORING_TOTAL_FIELD_NAMES = ["subtotal", "tax", "fees", "total_due", "tax_rate", "current_charges"]

_D = FieldScope.DOCUMENT
_R = FieldScope.ROW

CANONICAL_FIELDS: tuple[FieldDef, ...] = (
    FieldDef(name="output_type", scope=_D, type=FieldType.STRING, role=FieldRole.NONE,
             description="Layout category label; it does not change the fingerprint."),
    FieldDef(name="supplier_name", scope=_D, type=FieldType.STRING, required=True,
             description="Supplier name as printed."),
    FieldDef(name="supplier_aliases", scope=_D, type=FieldType.STRING, role=FieldRole.NONE,
             description="Other names the supplier prints for itself."),
    FieldDef(name="invoice_number", scope=_D, type=FieldType.STRING, required=True,
             label_hint="Invoice Number", role=FieldRole.IDENTIFIER,
             description="Invoice number as printed."),
    FieldDef(name="invoice_date", scope=_D, type=FieldType.DATE, required=True,
             label_hint="Invoice Date", description="Invoice issue date."),
    FieldDef(name="due_date", scope=_D, type=FieldType.DATE, label_hint="Due Date",
             description="Payment due date."),
    FieldDef(name="account_number", scope=_D, type=FieldType.STRING,
             label_hint="Account Number",
             description="Customer/account number identifying the billed account."),
    FieldDef(name="ban", scope=_D, type=FieldType.STRING,
             description="Secondary billing account number, when the document shows one."),
    FieldDef(name="billing_period_start", scope=_D, type=FieldType.DATE,
             description="Start of the billing period the invoice covers."),
    FieldDef(name="billing_period_end", scope=_D, type=FieldType.DATE,
             description="End of the billing period the invoice covers."),
    FieldDef(name="currency", scope=_D, type=FieldType.STRING,
             description="ISO currency code of the invoice."),
    FieldDef(name="po_number", scope=_D, type=FieldType.STRING,
             description="Purchase order number, when printed."),
    FieldDef(name="payment_terms", scope=_D, type=FieldType.STRING,
             description="Payment terms as printed (e.g. Net 30)."),
    FieldDef(name="source_page", scope=_D, type=FieldType.INTEGER,
             description="Page the header was read from."),
    FieldDef(name="confidence", scope=_D, type=FieldType.NUMBER,
             description="Extraction confidence for the document fields."),
    FieldDef(name="subtotal", scope=_D, type=FieldType.CURRENCY, role=FieldRole.SUBTOTAL,
             description="Pre-tax subtotal as printed."),
    FieldDef(name="tax", scope=_D, type=FieldType.CURRENCY, role=FieldRole.TAX,
             description="Invoice-level tax total as printed."),
    FieldDef(name="fees", scope=_D, type=FieldType.CURRENCY,
             description="Invoice-level fees and surcharges total."),
    FieldDef(name="current_charges", scope=_D, type=FieldType.CURRENCY, role=FieldRole.SUBTOTAL,
             description="Total of this period's charges (excluding prior balance)."),
    FieldDef(name="total_due", scope=_D, type=FieldType.CURRENCY, role=FieldRole.TOTAL,
             label_hint="Total Due", description="Amount due as printed."),
    FieldDef(name="tax_rate", scope=_D, type=FieldType.NUMBER, role=FieldRole.TAX_RATE,
             description="Invoice-level tax rate, when printed."),
    FieldDef(name="line_number", scope=_R, type=FieldType.INTEGER, required=True,
             description="Sequential line number."),
    FieldDef(name="service_id", scope=_R, type=FieldType.STRING, role=FieldRole.IDENTIFIER,
             description="Per-line service/item identifier (e.g. circuit or service number, SKU, line ID)."),
    FieldDef(name="billing_reference", scope=_R, type=FieldType.STRING, role=FieldRole.IDENTIFIER,
             description="Per-line contract/order/billing reference, when shown separately from the service id."),
    FieldDef(name="description", scope=_R, type=FieldType.STRING, required=True,
             description="Human-readable description of the charge."),
    FieldDef(name="charge_type", scope=_R, type=FieldType.ENUM, role=FieldRole.NONE,
             enum_values=CHARGE_TYPE_VALUES,
             description="Kind of charge; each fee/tax/credit/adjustment is its own line item."),
    FieldDef(name="amount", scope=_R, type=FieldType.CURRENCY, required=True, role=FieldRole.AMOUNT,
             description="Net (pre-tax) amount for this line; numeric, no currency symbol."),
    FieldDef(name="tax_amount", scope=_R, type=FieldType.CURRENCY, role=FieldRole.TAX,
             description="Per-line tax amount, only when tax is itemized per line (else null)."),
    FieldDef(name="currency", scope=_R, type=FieldType.STRING,
             description="ISO currency code of the line."),
    FieldDef(name="billing_period_start", scope=_R, type=FieldType.DATE,
             description="Start of the period this line covers."),
    FieldDef(name="billing_period_end", scope=_R, type=FieldType.DATE,
             description="End of the period this line covers."),
    FieldDef(name="quantity", scope=_R, type=FieldType.NUMBER,
             description="Quantity billed on this line."),
    FieldDef(name="unit_rate", scope=_R, type=FieldType.CURRENCY,
             description="Unit price on this line."),
    FieldDef(name="plan_cost", scope=_R, type=FieldType.CURRENCY,
             description="Plan/subscription portion of the line (wireless layouts)."),
    FieldDef(name="equipment_cost", scope=_R, type=FieldType.CURRENCY,
             description="Equipment portion of the line (wireless layouts)."),
    FieldDef(name="source_page", scope=_R, type=FieldType.INTEGER,
             description="Page the line was read from."),
    FieldDef(name="source_row_id", scope=_R, type=FieldType.STRING,
             description="Printed layout row the line was read from (e.g. p5.r12)."),
    FieldDef(name="confidence", scope=_R, type=FieldType.NUMBER,
             description="Extraction confidence for the line."),
)

# Fields a CanonicalInvoice / LineItem cannot be built without. They are read
# whether or not the profile lists them, so a profile's field list is purely
# "what else to read" plus hints on these.
ALWAYS_ON_KEYS: frozenset[tuple[FieldScope, str]] = frozenset({
    (_D, "output_type"), (_D, "supplier_name"), (_D, "currency"),
    (_D, "source_page"), (_D, "confidence"),
    (_R, "line_number"), (_R, "description"), (_R, "charge_type"), (_R, "amount"),
    (_R, "currency"), (_R, "source_page"), (_R, "confidence"), (_R, "source_row_id"),
})

# The catalogue's own printed-label defaults. A profile field that still carries
# one of these (and no date format) is treated as "no supplier hint given".
DEFAULT_LABELS: dict[tuple[FieldScope, str], str] = {
    (f.scope, f.name): f.label_hint for f in CANONICAL_FIELDS if f.label_hint
}

DOCUMENT_DATE_FIELD_NAMES = frozenset(
    f.name for f in CANONICAL_FIELDS if f.scope == _D and f.type == FieldType.DATE
)
ROW_DATE_FIELD_NAMES = frozenset(
    f.name for f in CANONICAL_FIELDS if f.scope == _R and f.type == FieldType.DATE
)

COMPUTED_SOURCES = ("computed.line_tax",)


def catalogue_by_key() -> dict[tuple[FieldScope, str], FieldDef]:
    return {(f.scope, f.name): f for f in CANONICAL_FIELDS}


def catalogue_field(scope: FieldScope | str, name: str) -> FieldDef | None:
    scope_val = FieldScope(scope) if isinstance(scope, str) else scope
    return catalogue_by_key().get((scope_val, name))


def field_path(field: FieldDef) -> str:
    prefix = "field" if field.scope == FieldScope.DOCUMENT else "row"
    return f"{prefix}.{field.name}"


def catalogue_paths() -> list[str]:
    """Every catalogue field as a column source path (``field.x`` / ``row.x``)."""
    return [field_path(f) for f in CANONICAL_FIELDS]


def is_catalogue_field(field: FieldDef) -> bool:
    return (field.scope, field.name) in catalogue_by_key()


def is_default_label(field: FieldDef) -> bool:
    """True when the field carries no supplier-specific label hint: either no
    label at all, or exactly the catalogue's own default for that field."""
    label = (field.label_hint or "").strip()
    if not label:
        return True
    return DEFAULT_LABELS.get((field.scope, field.name)) == label


def default_field_set() -> FieldSchema:
    """The whole catalogue as an in-memory field set (no profile)."""
    return FieldSchema(
        schema_id="catalogue",
        name="Catalogue",
        fields=[f.model_copy() for f in CANONICAL_FIELDS],
    )
