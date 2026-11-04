"""Column sets for tests that render a deliverable.

The product ships no default column set: every profile configures its own.
Tests that only care about the row builder, writer or preview still need a
concrete column list, so this is the eight-column layout the corpus fixtures
were recorded with, expressed the way a profile would store it.
"""

from __future__ import annotations

from polaris.fields.schema import FieldDef, FieldScope
from polaris.output.columns import OutputColumn
from polaris.output.mapper import ColumnDef
from polaris.profiles.contract import columns_to_defs

# The fields a profile delivering the eight-column layout reads (the catalogue
# picks the compact extractor asked for before profiles owned their field list).
STANDARD_FIELDS: list[FieldDef] = [
    FieldDef(name=name, scope=FieldScope.DOCUMENT)
    for name in (
        "invoice_number", "invoice_date", "due_date", "account_number",
        "subtotal", "tax", "fees", "current_charges", "total_due", "tax_rate",
    )
] + [
    FieldDef(name=name, scope=FieldScope.ROW)
    for name in ("service_id", "billing_reference", "tax_amount")
]

STANDARD_OUTPUT_COLUMNS: list[OutputColumn] = [
    OutputColumn(header="EXT_SERVICEID", source="row.service_id", fallback="row.billing_reference", width=20),
    OutputColumn(header="EXT_BILLINGREFERENCE", source="row.billing_reference", fallback="row.service_id", width=20),
    OutputColumn(header="EXT_DATE", source="field.invoice_date", width=14),
    OutputColumn(header="formula", source="field.due_date", fallback="field.invoice_date", width=14),
    OutputColumn(header="EXT_AMOUNT", source="row.amount", width=14, number_format="#,##0.##"),
    OutputColumn(header="EXT_ACCOUNT", source="field.account_number", width=16),
    OutputColumn(header="EXT_INVOICENUMBER", source="field.invoice_number", width=20),
    OutputColumn(header="EXT_TAX", source="computed.line_tax", width=14, number_format="#,##0.00"),
]

STANDARD_COLUMNS: list[ColumnDef] = columns_to_defs(STANDARD_OUTPUT_COLUMNS)
STANDARD_HEADERS: list[str] = [c.xlsx_header for c in STANDARD_COLUMNS]


def defs(columns) -> list[ColumnDef]:
    """``OutputColumn``/dict list (or an object with ``.columns``) to ColumnDefs."""
    if hasattr(columns, "columns"):
        columns = columns.columns
    return columns_to_defs(columns)
