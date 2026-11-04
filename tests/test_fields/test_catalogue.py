"""The field catalogue is the fixed vocabulary every other layer agrees on."""

from polaris.extraction.compact_chunked import (
    DEFAULT_DOC_FIELDS,
    DEFAULT_ROW_FIELDS,
    DOC_ALIAS_TO_FIELD,
    ROW_ALIAS_TO_FIELD,
)
from polaris.fields import catalogue
from polaris.fields.coercion import DOCUMENT_DATE_FIELDS, ROW_DATE_FIELDS
from polaris.fields.schema import FieldDef, FieldScope, FieldType
from polaris.output.mapper import _BARE_TOTAL_FIELDS
from polaris.validation.schema import _HEADER_KEYS, _TOTAL_KEYS


def _names(scope: FieldScope) -> set[str]:
    return {f.name for f in catalogue.CANONICAL_FIELDS if f.scope == scope}


def test_catalogue_has_the_expected_shape():
    assert len(catalogue.CANONICAL_FIELDS) == 38
    keys = [(f.scope, f.name) for f in catalogue.CANONICAL_FIELDS]
    assert len(keys) == len(set(keys)), "duplicate (scope, name)"
    assert catalogue.ALWAYS_ON_KEYS <= set(keys)


def test_compact_aliases_name_only_catalogue_fields():
    doc = _names(FieldScope.DOCUMENT)
    row = _names(FieldScope.ROW)
    assert set(DOC_ALIAS_TO_FIELD.values()) <= doc
    assert set(ROW_ALIAS_TO_FIELD.values()) - {"_row_ref"} <= row
    assert DEFAULT_DOC_FIELDS <= doc
    assert DEFAULT_ROW_FIELDS <= row


def test_canonical_invoice_keys_match_the_catalogue():
    doc = _names(FieldScope.DOCUMENT)
    assert _HEADER_KEYS <= doc
    assert _TOTAL_KEYS <= doc
    assert _BARE_TOTAL_FIELDS <= doc


def test_date_sets_are_derived_from_field_types():
    assert catalogue.DOCUMENT_DATE_FIELD_NAMES == DOCUMENT_DATE_FIELDS
    assert catalogue.ROW_DATE_FIELD_NAMES == ROW_DATE_FIELDS


def test_authoring_name_lists_are_catalogue_fields():
    doc = _names(FieldScope.DOCUMENT)
    row = _names(FieldScope.ROW)
    assert set(catalogue.AUTHORING_HEADER_FIELD_NAMES) <= doc
    assert set(catalogue.AUTHORING_TOTAL_FIELD_NAMES) <= doc
    assert set(catalogue.AUTHORING_ITEM_FIELD_NAMES) <= row


def test_lookup_helpers():
    assert catalogue.catalogue_field("row", "amount").type == FieldType.CURRENCY
    assert catalogue.catalogue_field(FieldScope.DOCUMENT, "nope") is None
    assert "field.invoice_number" in catalogue.catalogue_paths()
    assert "row.source_row_id" in catalogue.catalogue_paths()
    custom = FieldDef(name="site_code", scope=FieldScope.ROW)
    assert catalogue.is_catalogue_field(custom) is False


def test_default_field_set_is_a_copy_of_the_catalogue():
    a = catalogue.default_field_set()
    b = catalogue.default_field_set()
    a.fields[0].label_hint = "mutated"
    assert b.fields[0].label_hint != "mutated"
    assert [f.name for f in b.fields] == [f.name for f in catalogue.CANONICAL_FIELDS]
