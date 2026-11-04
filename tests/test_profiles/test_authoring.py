"""Offline unit tests for AI profile authoring (no OpenAI calls)."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from polaris.fields.catalogue import CANONICAL_FIELDS, default_field_set
from polaris.fields.schema import FieldDef, FieldRole, FieldScope, FieldType
from polaris.output.columns import OutputColumn
from polaris.profiles import authoring
from polaris.profiles.authoring import (
    InvoiceEvidence,
    author_profile,
    authoring_field_set,
    build_profile_authoring_schema,
    draft_to_supplier_profile_dict,
    supplier_profile_to_draft,
)
from polaris.profiles.contract import field_set, validate_output_columns
from polaris.profiles.schema import SupplierProfile
from tests.output_columns import STANDARD_OUTPUT_COLUMNS


def _column(header: str, source: str, **kw) -> dict:
    return {"header": header, "source": source, "fallback": None, "transforms": [], "number_format": None,
            "width": None, "reason": "test", **kw}


def _field(name: str, scope: str = "document", **kw) -> dict:
    return {"name": name, "scope": scope, "type": None, "role": None, "label_hint": None, "date_format": None,
            "required": False, "description": None, **kw}


def _flat_draft() -> dict:
    return {
        "canonical_name": "Acme",
        "aliases": ["Acme Inc", "Acme Telecom"],
        "output_type": "standard",
        "notes": "Header is a label/value table on page 1.",
        "fields": [
            _field("invoice_number", label_hint="Invoice No"),
            _field("due_date", label_hint="Payment Due", date_format="%d/%m/%Y"),
            _field("service_id", "row"),
            _field("site_code", "row", type="string", role="none", label_hint="Site"),
        ],
        "output_columns": [
            _column("EXT_SERVICEID", "row.service_id"),
            _column("EXT_DUE", "field.due_date"),
            _column("SITE", "row.site_code", transforms=["uppercase"]),
        ],
        "detail_start_marker": "Service Charges",
        "detail_end_marker": None,
        "line_item_granularity": "per_charge_row",
        "service_id_preference": "first_identifier",
        "billing_reference_preference": "same_as_service_id",
        "service_id_column_label": "Service Number",
        "billing_reference_column_label": None,
        "amount_column_label": "Amount",
        "tax_amount_column_label": "Tax",
        "amount_source": "table_charges_column",
        "tax_source": "table_tax_column",
        "tax_output_mode": "extract_exact",
        "tax_rate_source": None,
        "service_id_value_pattern": None,
        "billing_reference_value_pattern": None,
        "detail_table_anchors": ["Service Charges"],
        "table_column_labels": ["Service", "Amount"],
        "subtotal_keywords": [],
        "tax_keywords": ["VAT"],
        "skip_row_keywords": ["Total Current Charges"],
        "include_zero_amount_line_items": False,
        "require_line_item_identifier": True,
    }


def test_schema_pins_column_sources_to_the_field_set_and_lets_fields_be_custom():
    schema = build_profile_authoring_schema(default_field_set())
    profile_props = schema["schema"]["properties"]["profile"]["properties"]
    assert schema["strict"] is True
    field_item = profile_props["fields"]["items"]["properties"]
    assert "enum" not in field_item["name"]  # custom names are allowed
    assert field_item["scope"]["enum"] == ["document", "row"]
    assert field_item["date_format"] == {"type": ["string", "null"]}
    column = profile_props["output_columns"]["items"]["properties"]
    assert "row.billing_period_start" in column["source"]["enum"]
    assert "computed.line_tax" in column["source"]["enum"]
    assert column["fallback"]["type"] == ["string", "null"]
    assert column["transforms"]["items"]["enum"] == ["digits_only", "trim", "uppercase", "lowercase"]
    assert "uniqueItems" not in column["transforms"]


def test_custom_fields_in_play_become_mappable_sources():
    vocabulary = authoring_field_set(None, [_field("site_code", "row", type="string")])
    schema = build_profile_authoring_schema(vocabulary)
    column = schema["schema"]["properties"]["profile"]["properties"]["output_columns"]["items"]["properties"]
    assert "row.site_code" in column["source"]["enum"]
    assert len(vocabulary.fields) == len(CANONICAL_FIELDS) + 1


def test_draft_maps_to_valid_supplier_profile():
    profile_dict = draft_to_supplier_profile_dict({"profile": _flat_draft()})
    profile_dict["profile_id"] = "acme.standard.v1"
    profile = SupplierProfile.model_validate(profile_dict)

    assert profile.identity.canonical_name == "Acme"
    assert "Acme Telecom" in profile.identity.aliases
    assert profile.line_item_hints.line_item_granularity == "per_charge_row"
    assert profile.line_item_hints.service_id_column_label == "Service Number"
    assert profile.line_item_hints.tax_output_mode == "extract_exact"
    assert profile.require_line_item_identifier is True

    by_key = {(f.scope, f.name): f for f in profile.fields}
    # A catalogue pick keeps the catalogue's type and role and takes the hints.
    number = by_key[(FieldScope.DOCUMENT, "invoice_number")]
    assert number.role == FieldRole.IDENTIFIER and number.label_hint == "Invoice No"
    due = by_key[(FieldScope.DOCUMENT, "due_date")]
    assert due.type == FieldType.DATE and due.date_format == "%d/%m/%Y"
    # A custom field is taken as written.
    site = by_key[(FieldScope.ROW, "site_code")]
    assert site.type == FieldType.STRING and site.label_hint == "Site"

    assert [c.header for c in profile.output_columns] == ["EXT_SERVICEID", "EXT_DUE", "SITE"]
    assert profile.output_columns[2].transforms == ["uppercase"]
    assert validate_output_columns(profile.output_columns, field_set(profile)) == []


def test_draft_dedupes_columns_by_header_and_fields_by_key():
    draft = _flat_draft()
    draft["output_columns"].append(_column("EXT_SERVICEID", "row.billing_reference"))
    draft["fields"].append(_field("service_id", "row", label_hint="Circuit"))
    result = draft_to_supplier_profile_dict({"profile": draft})
    assert [c["header"] for c in result["output_columns"]] == ["EXT_SERVICEID", "EXT_DUE", "SITE"]
    assert result["output_columns"][0]["source"] == "row.service_id"
    service = next(f for f in result["fields"] if f["name"] == "service_id")
    assert service["label_hint"] == "Circuit"  # the later entry wins


def test_draft_omitting_fields_and_columns_leaves_them_to_the_source_profile():
    draft = _flat_draft()
    del draft["fields"]
    del draft["output_columns"]
    result = draft_to_supplier_profile_dict({"profile": draft})
    assert "fields" not in result and "output_columns" not in result


def test_legacy_field_path_entries_still_resolve():
    draft = _flat_draft()
    draft["fields"] = [{"field_path": "row.billing_period_start", "label_hint": "Period", "date_format": "%d/%m/%Y"}]
    result = draft_to_supplier_profile_dict({"profile": draft})
    assert result["fields"] == [{
        "name": "billing_period_start", "scope": "row", "type": "date", "role": "none",
        "label_hint": "Period", "date_format": "%d/%m/%Y", "required": False,
    }]


def test_profile_round_trips_through_the_draft():
    profile_dict = draft_to_supplier_profile_dict({"profile": _flat_draft()})
    profile_dict["profile_id"] = "acme.round-trip"
    profile = SupplierProfile.model_validate(profile_dict)

    restored = supplier_profile_to_draft(profile)["profile"]
    assert [(f["name"], f["scope"], f["label_hint"], f["date_format"]) for f in restored["fields"]] == [
        ("invoice_number", "document", "Invoice No", None),
        ("due_date", "document", "Payment Due", "%d/%m/%Y"),
        ("service_id", "row", None, None),
        ("site_code", "row", "Site", None),
    ]
    assert [c["header"] for c in restored["output_columns"]] == ["EXT_SERVICEID", "EXT_DUE", "SITE"]
    assert restored["output_columns"][2]["transforms"] == ["uppercase"]
    again = draft_to_supplier_profile_dict({"profile": restored})
    assert again["fields"] == profile_dict["fields"]
    assert again["output_columns"] == profile_dict["output_columns"]


def test_author_profile_with_stubbed_openai(monkeypatch):
    captured = {}

    def create(**kwargs):
        captured["schema_name"] = kwargs["response_format"]["json_schema"]["name"]
        captured["messages"] = kwargs["messages"]
        payload = {
            "assistant_message": "Mapped due date and set per-charge grouping.",
            "open_questions": ["Is VAT itemized per line?"],
            "confidence": 0.82,
            "profile": _flat_draft(),
        }
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=40),
        )

    client = MagicMock()
    client.chat.completions.create.side_effect = create
    monkeypatch.setattr(authoring, "get_ai_client", lambda *a, **k: client)

    evidence = [
        InvoiceEvidence(
            label="acme_jan.pdf",
            page_texts=["[p1] Invoice ... Service Charges ..."],
            target={
                "header": {"invoice_number": "INV1"},
                "totals": {"subtotal": "100.00", "tax": "8.25"},
                "line_items": [{"amount": "100.00", "tax_amount": "8.25"}],
            },
            blueprint_context={
                "filename": "acme_jan.xls",
                "sheet_name": "Invoice Data",
                "raw_headers": ["EXT_SERVICEID", "EXT_AMOUNT", "EXT_TAX"],
                "aligned_rows": [["SVC1", "", "", "", "100.00", "", "", "8.25"]],
                "row_count": 1,
                "sample_rows": [["SVC1", "", "", "", "100.00", "", "", "8.25"]],
                "totals": {"amount": "100.00", "tax": "8.25"},
                "warnings": [],
            },
            diff_feedback="exact match",
        )
    ]
    result = author_profile(
        field_set=default_field_set(),
        columns=STANDARD_OUTPUT_COLUMNS,
        invoices=evidence,
        conversation=[{"role": "user", "content": "Service ID is the leftmost number, one row per charge."}],
        current_draft=None,
    )

    assert captured["schema_name"] == "supplier_profile_draft"
    assert result.assistant_message.startswith("Mapped")
    assert result.open_questions == ["Is VAT itemized per line?"]
    assert result.confidence == 0.82
    assert result.tokens_input == 100 and result.tokens_output == 40
    assert result.draft["profile"]["line_item_granularity"] == "per_charge_row"
    system_prompt = captured["messages"][0]["content"]
    user_prompt = captured["messages"][1]["content"]
    assert "source" in system_prompt and "truth" in system_prompt
    assert "Use the blueprint to learn what" in system_prompt
    assert "PDF as evidence for printed facts and totals" in system_prompt
    assert "Never relabel invoice_date" in system_prompt
    assert "COMPLETE list of fields" in system_prompt
    assert "COMPLETE ordered list of delivered columns" in system_prompt
    assert "its headers ARE the contract" in system_prompt
    assert "Explain every meaningful difference" in system_prompt
    assert "Build an internal extraction plan" in system_prompt
    assert "Use the available extraction toolkit" in system_prompt
    assert "field_overrides" not in system_prompt and "OutputSpec" not in system_prompt
    assert "blueprint_context" in user_prompt
    assert "baseline_extracted_evidence" in user_prompt
    assert "field_catalogue" in user_prompt
    assert "current_output_columns" in user_prompt
    assert "allowed_output_sources" in user_prompt
    assert "blueprint_vs_invoice_summary" in user_prompt
    assert "preview_vs_blueprint_diff" in user_prompt


def test_schema_allows_blueprint_amount_and_tax_hints():
    profile_props = build_profile_authoring_schema(default_field_set())["schema"]["properties"]["profile"][
        "properties"]

    assert profile_props["amount_source"]["enum"] == [
        "group_total", "first_amount", "label_amount", "label_amount_minus_tax", "table_charges_column", None]
    assert profile_props["tax_source"]["enum"] == [
        "none", "label_amount", "group_total_minus_amount", "table_tax_column", None]
    assert profile_props["tax_output_mode"]["enum"] == ["auto", "extract_exact", "calculate", "none", None]
    assert "service_id_value_pattern" in profile_props
    assert "billing_reference_value_pattern" in profile_props


def test_blueprint_summary_warns_when_xlsx_values_do_not_match_pdf_truth():
    summary = authoring._blueprint_vs_invoice_summary(
        {
            "aligned_headers": ["EXT_SERVICEID", "EXT_DATE", "EXT_AMOUNT", "EXT_INVOICENUMBER", "EXT_TAX"],
            "aligned_rows": [["441101218", "07/01/2026", "608.48", "792254753", "406.23"]],
            "row_count": 1,
            "totals": {"amount": "608.48", "tax": "406.23"},
        },
        {
            "header": {"invoice_number": "788263904", "invoice_date": "2026-06-01"},
            "totals": {"subtotal": "25551.43", "tax": "3368.85"},
            "line_items": [],
        },
    )

    assert summary is not None
    assert summary["warnings"] == [
        "Blueprint amount total differs from the printed invoice subtotal; "
        "explain the delivery semantics or reconcile the difference.",
        "Blueprint tax total differs from the printed invoice tax total; "
        "explain the delivery semantics or reconcile the difference.",
        "Blueprint invoice number differs from the baseline header extraction; verify the intended output mapping.",
        "Blueprint date differs from the baseline invoice date; check billing-period "
        "or row-date fields before choosing an output mapping.",
    ]


def test_blueprint_summary_identifies_row_billing_period_as_date_mapping_evidence():
    summary = authoring._blueprint_vs_invoice_summary(
        {
            "aligned_headers": ["EXT_DATE", "formula"],
            "aligned_rows": [["07/01/2026", "07/31/2026"]],
            "row_count": 1,
        },
        {
            "header": {"invoice_date": "2026-08-03", "due_date": "2026-08-31"},
            "totals": {},
            "line_items": [{
                "billing_period_start": "2026-07-01",
                "billing_period_end": "2026-07-31",
            }],
        },
        columns=[
            OutputColumn(header="EXT_DATE", source="field.invoice_date"),
            OutputColumn(header="formula", source="field.due_date"),
        ],
        field_set=default_field_set(),
    )

    evidence = {item["output_header"]: item for item in summary["output_mapping_evidence"]}
    assert evidence["EXT_DATE"]["matching_alternative_sources"] == ["row.billing_period_start"]
    assert evidence["formula"]["matching_alternative_sources"] == ["row.billing_period_end"]


def test_authoring_field_set_merges_source_profile_customs():
    source = SupplierProfile(
        profile_id="s", identity={"canonical_name": "S"},
        fields=[FieldDef(name="cost_centre", scope=FieldScope.DOCUMENT, type=FieldType.STRING)],
    )
    vocabulary = authoring_field_set(field_set(source), [_field("site_code", "row", type="number")])
    paths = {f"{f.scope.value}.{f.name}" for f in vocabulary.fields}
    assert {"document.cost_centre", "row.site_code"} <= paths
