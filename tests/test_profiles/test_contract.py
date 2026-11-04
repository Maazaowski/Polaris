"""What a profile reads and delivers is resolved in one place: profiles/contract."""

from datetime import date
from decimal import Decimal

from polaris.fields.catalogue import ALWAYS_ON_KEYS
from polaris.fields.schema import FieldDef, FieldRole, FieldScope, FieldType
from polaris.models.schema import ExtractionModel
from polaris.output.columns import OutputColumn
from polaris.output.xlsx_writer import build_output_rows
from polaris.profiles import contract
from polaris.profiles.schema import AdvancedHints, LineItemHints, SupplierIdentity, SupplierProfile
from polaris.validation.schema import (
    CanonicalInvoice,
    ExtractionMetadata,
    ExtractionPath,
    InvoiceHeader,
    LineItem,
)


def _profile(**kw) -> SupplierProfile:
    base = dict(profile_id="acme.v1", identity=SupplierIdentity(canonical_name="Acme"))
    base.update(kw)
    return SupplierProfile(**base)


def _model(**kw) -> ExtractionModel:
    return ExtractionModel(model_id="m", supplier_profile_id="acme.v1", supplier="Acme", **kw)


def _invoice(**kw) -> CanonicalInvoice:
    defaults = dict(
        intake_id="t1",
        header=InvoiceHeader(
            supplier_name="Acme", invoice_number="INV-1", invoice_date=date(2026, 1, 2), account_number="A1",
        ),
        line_items=[
            LineItem(line_number=1, service_id="S1", billing_reference="B1", description="svc",
                     amount=Decimal("100.00")),
        ],
        metadata=ExtractionMetadata(extraction_path=ExtractionPath.AI),
    )
    defaults.update(kw)
    return CanonicalInvoice(**defaults)


# ---------------------------------------------------------------- fields


def test_empty_profile_reads_only_the_always_on_fields():
    fs = contract.field_set(_profile())
    assert {(f.scope, f.name) for f in fs.fields} == set(ALWAYS_ON_KEYS)


def test_no_profile_reads_the_whole_catalogue():
    assert len(contract.field_set(None).fields) == 38


def test_catalogue_pick_takes_type_and_role_from_the_catalogue_and_hints_from_the_profile():
    profile = _profile(fields=[
        FieldDef(name="invoice_number", scope=FieldScope.DOCUMENT, type=FieldType.STRING,
                 role=FieldRole.NONE, label_hint="Document No."),
        FieldDef(name="invoice_date", scope=FieldScope.DOCUMENT, date_format="%d/%m/%Y"),
    ])
    fs = contract.field_set(profile)
    number = fs.field_by_name("invoice_number")
    assert number.role == FieldRole.IDENTIFIER and number.label_hint == "Document No."
    inv_date = next(f for f in fs.document_fields() if f.name == "invoice_date")
    assert inv_date.type == FieldType.DATE
    assert inv_date.date_format == "%d/%m/%Y"
    assert inv_date.label_hint == "Invoice Date"  # catalogue default fills in


def test_custom_field_is_taken_as_written_and_listed_after_the_catalogue():
    custom = FieldDef(name="site_code", scope=FieldScope.ROW, type=FieldType.STRING, label_hint="Site")
    fs = contract.field_set(_profile(fields=[custom]))
    assert fs.fields[-1] == custom
    assert fs.row_fields()[-1].name == "site_code"


def test_validate_fields_rules():
    bad = [
        FieldDef(name="Bad Name", scope=FieldScope.ROW),
        FieldDef(name="sn", scope=FieldScope.DOCUMENT),
        FieldDef(name="amount", scope=FieldScope.DOCUMENT, type=FieldType.STRING),
        FieldDef(name="kind", scope=FieldScope.ROW, type=FieldType.ENUM),
        FieldDef(name="kind", scope=FieldScope.ROW, type=FieldType.ENUM),
    ]
    issues = contract.validate_fields(bad)
    assert any("Bad Name" in i for i in issues)
    assert any("'sn' clashes" in i for i in issues)
    assert any("reuses a catalogue name" in i for i in issues)
    assert any("requires enum_values" in i for i in issues)
    assert any("listed more than once" in i for i in issues)
    assert contract.validate_fields([FieldDef(name="site_code", scope=FieldScope.ROW)]) == []


# ---------------------------------------------------------------- columns


def test_columns_precedence_template_then_profile_then_nothing():
    profile = _profile(output_columns=[OutputColumn(header="P", source="row.amount")])
    model = _model(output_columns=[OutputColumn(header="T", source="row.amount")])
    assert [c.header for c in contract.output_columns(profile, model)] == ["T"]
    assert [c.header for c in contract.output_columns(profile, _model())] == ["P"]
    assert contract.output_columns(_profile(), _model()) == []
    assert contract.delivery_columns(_profile()) == []


def test_delivery_columns_normalise_paths_and_carry_value_types():
    profile = _profile(
        fields=[
            FieldDef(name="site_code", scope=FieldScope.ROW, type=FieldType.NUMBER),
            FieldDef(name="invoice_date", scope=FieldScope.DOCUMENT),
            FieldDef(name="service_id", scope=FieldScope.ROW),
            FieldDef(name="total_due", scope=FieldScope.DOCUMENT),
        ],
        output_columns=[
            OutputColumn(header="DATE", source="field.invoice_date"),
            OutputColumn(header="ID", source="line_item.service_id"),
            OutputColumn(header="SITE", source="row.site_code"),
            OutputColumn(header="TOTAL", source="field.total_due"),
        ],
    )
    defs = contract.delivery_columns(profile)
    assert [c.canonical_path for c in defs] == [
        "header.invoice_date", "line_item.service_id", "line_item.site_code", "total_due",
    ]
    assert [c.value_type for c in defs] == ["date", "string", "number", "currency"]


def test_billing_reference_rule_drops_the_service_id_fallback():
    columns = [OutputColumn(header="REF", source="row.billing_reference", fallback="row.service_id")]
    plain = _profile(output_columns=columns)
    assert contract.delivery_columns(plain)[0].fallback_path == "line_item.service_id"
    distinct = _profile(
        output_columns=columns,
        advanced=AdvancedHints(line_item_hints=LineItemHints(billing_reference_preference="none")),
    )
    assert contract.delivery_columns(distinct)[0].fallback_path is None


def test_custom_fields_flow_into_delivered_rows():
    profile = _profile(
        fields=[
            FieldDef(name="site_code", scope=FieldScope.ROW),
            FieldDef(name="cost_centre", scope=FieldScope.DOCUMENT),
        ],
        output_columns=[
            OutputColumn(header="SITE", source="row.site_code", transforms=["uppercase"]),
            OutputColumn(header="CC", source="field.cost_centre"),
        ],
    )
    invoice = _invoice()
    invoice.rows[0]["site_code"] = "lhr-01"
    invoice.fields["cost_centre"] = "CC-9"
    assert build_output_rows(invoice, contract.delivery_columns(profile)) == [["LHR-01", "CC-9"]]


def test_validate_output_columns_rules():
    fs = contract.field_set(_profile(fields=[FieldDef(name="invoice_date", scope=FieldScope.DOCUMENT)]))
    issues = contract.validate_output_columns([
        OutputColumn(header="", source="row.amount"),
        OutputColumn(header="A", source="row.amount"),
        OutputColumn(header="A", source="row.nope"),
        OutputColumn(header="B", source=""),
        OutputColumn(header="C", source="computed.line_tax", transforms=["trim"]),
        OutputColumn(header="D", source="computed.magic"),
        OutputColumn(header="E", source="field.po_number"),
    ], fs)
    assert "every column requires a non-empty header" in issues
    assert "column headers must be unique: A" in issues
    assert "column 'A' references unknown row field 'nope'" in issues
    assert "column 'B' requires a source" in issues
    assert "column 'C' cannot transform a computed value" in issues
    assert "column 'D' references unknown computed value 'computed.magic'" in issues
    assert "column 'E' references unknown document field 'po_number'" in issues
    ok = [OutputColumn(header="DATE", source="field.invoice_date", fallback="line_item.description")]
    assert contract.validate_output_columns(ok, fs) == []


def test_date_format_issues_name_the_unformatted_date_sources():
    fs = contract.field_set(_profile(fields=[
        FieldDef(name="invoice_date", scope=FieldScope.DOCUMENT),
        FieldDef(name="due_date", scope=FieldScope.DOCUMENT, date_format="%d/%m/%Y"),
    ]))
    columns = [
        OutputColumn(header="D", source="field.invoice_date"),
        OutputColumn(header="E", source="field.due_date"),
    ]
    assert contract.date_format_issues(columns, fs) == [
        "Mapped date field 'field.invoice_date' requires an explicit printed date format.",
    ]


def test_readiness_issues_block_training_without_fields_or_columns():
    draft = _profile(status="draft")
    assert contract.readiness_issues(draft) == []
    training = _profile(status="training")
    issues = contract.readiness_issues(training)
    assert "No fields to read are configured; add at least one field" in issues
    assert "No output columns are configured; add at least one delivered column" in issues
    ready = _profile(
        status="training",
        fields=[FieldDef(name="invoice_number", scope=FieldScope.DOCUMENT)],
        output_columns=[OutputColumn(header="N", source="field.invoice_number")],
    )
    assert contract.readiness_issues(ready) == []


def test_suggest_columns_from_headers_dedupes_and_leaves_sources_empty():
    out = contract.suggest_columns_from_headers(["EXT_ID", " ", "ext_id", "Amount"])
    assert [(c.header, c.source) for c in out] == [("EXT_ID", ""), ("Amount", "")]


# ---------------------------------------------------------------- raw workbook


def test_raw_workbook_columns_list_every_extracted_row_field():
    invoice = _invoice()
    invoice.rows[0]["site_code"] = "x"
    headers = [c.xlsx_header for c in contract.raw_workbook_columns(invoice)]
    assert headers[:3] == ["service_id", "billing_reference", "description"]
    assert "amount" in headers and headers[-1] == "site_code"
    assert "line_number" not in headers and "confidence" not in headers
    names = [name for name, _ in contract.raw_document_fields(invoice)]
    assert names[:2] == ["supplier_name", "invoice_number"]
