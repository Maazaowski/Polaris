"""The compact AI calls ask only for what the profile reads (plus what cannot
be left out), and custom fields travel under their own names."""

from polaris.extraction.compact_chunked import (
    DEFAULT_DOC_FIELDS,
    DEFAULT_ROW_FIELDS,
    _compact_field_selection,
    build_compact_line_item_schema,
    build_compact_scalar_schema,
    compact_to_legacy_raw,
)
from polaris.fields.schema import FieldDef, FieldScope, FieldType
from polaris.output.columns import OutputColumn
from polaris.profiles.contract import field_set
from polaris.profiles.schema import SupplierIdentity, SupplierProfile
from polaris.validation.document_io import build_extracted_from_ai_raw
from polaris.validation.schema import ExtractionMetadata, ExtractionPath


def _profile(**kw) -> SupplierProfile:
    base = dict(profile_id="acme.v1", identity=SupplierIdentity(canonical_name="Acme"))
    base.update(kw)
    return SupplierProfile(**base)


def test_no_profile_uses_the_catalogue_defaults():
    assert _compact_field_selection(None, None) == (set(DEFAULT_DOC_FIELDS), set(DEFAULT_ROW_FIELDS))


def test_selection_is_the_profile_picks_plus_the_base_and_column_needs():
    profile = _profile(
        fields=[
            FieldDef(name="invoice_number", scope=FieldScope.DOCUMENT),
            FieldDef(name="service_id", scope=FieldScope.ROW),
            FieldDef(name="site_code", scope=FieldScope.ROW),
            FieldDef(name="output_type", scope=FieldScope.DOCUMENT),  # no alias, not custom: ignored
        ],
        output_columns=[
            OutputColumn(header="DATE", source="field.invoice_date"),
            OutputColumn(header="TAX", source="computed.line_tax"),
        ],
    )
    doc, row = _compact_field_selection(profile, field_set(profile))
    assert doc == {"supplier_name", "currency", "invoice_number", "tax_rate", "tax", "subtotal"}
    assert row == {"charge_type", "amount", "service_id", "site_code", "tax_amount"}
    # invoice_date is a column source but the profile does not read it: not widened in.
    assert "invoice_date" not in doc


def test_custom_fields_become_typed_properties_keyed_by_name():
    profile = _profile(fields=[
        FieldDef(name="site_code", scope=FieldScope.ROW, type=FieldType.STRING),
        FieldDef(name="units", scope=FieldScope.ROW, type=FieldType.NUMBER),
        FieldDef(name="cost_centre", scope=FieldScope.DOCUMENT, type=FieldType.ENUM, enum_values=["A", "B"]),
    ])
    fs = field_set(profile)
    doc, row = _compact_field_selection(profile, fs)
    scalars = build_compact_scalar_schema(doc, fs)["schema"]["properties"]["h"]["properties"]
    rows = build_compact_line_item_schema(row, fs)["schema"]["properties"]["rows"]["items"]["properties"]
    assert scalars["cost_centre"] == {"type": ["string", "null"], "enum": ["A", "B", None]}
    assert rows["site_code"] == {"type": ["string", "null"]}
    assert rows["units"] == {"type": ["number", "null"]}
    assert "s" not in rows  # service_id was not picked
    assert "a" in rows and "c" in rows  # amount and charge_type are always read


def test_custom_values_round_trip_and_source_row_id_survives():
    profile = _profile(fields=[
        FieldDef(name="site_code", scope=FieldScope.ROW),
        FieldDef(name="cost_centre", scope=FieldScope.DOCUMENT),
    ])
    raw = compact_to_legacy_raw(
        {
            "h": {"sn": "Acme", "in": "INV-1", "id": "2026-01-02", "cu": "USD", "cost_centre": "CC-9"},
            "rows": [{"r": "p1.r7", "d": "svc", "c": "recurring", "a": 10.5, "site_code": "lhr"}],
        },
        supplier_name="Acme",
    )
    assert raw["header"]["cost_centre"] == "CC-9"
    assert raw["line_items"][0]["site_code"] == "lhr"
    doc = build_extracted_from_ai_raw(
        raw, intake_id="t", field_schema=field_set(profile),
        metadata=ExtractionMetadata(extraction_path=ExtractionPath.AI),
    )
    assert doc.fields["cost_centre"] == "CC-9"
    assert doc.rows[0]["site_code"] == "lhr"
    assert doc.rows[0]["source_row_id"] == "p1.r7"
    # Fields the profile does not read are dropped even when the AI returned them.
    assert "invoice_number" not in doc.fields
