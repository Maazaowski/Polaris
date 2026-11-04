"""Migration 024 embeds what a legacy profile resolved to, exactly."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "versions" / "024_embed_profile_contract.py"


@pytest.fixture(scope="module")
def m():
    spec = importlib.util.spec_from_file_location("migration_024", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _legacy(**extra) -> dict:
    base = {
        "profile_id": "acme.v1",
        "identity": {"canonical_name": "Acme"},
        "output_spec_id": "standard.8col",
        "field_schema_id": "invoice.standard",
        "field_overrides": [],
        "output_mapping_overrides": [],
    }
    base.update(extra)
    return base


def _by_key(fields: list[dict]) -> dict[tuple[str, str], dict]:
    return {(f["scope"], f["name"]): f for f in fields}


def test_untouched_standard_profile_reads_the_default_sets_and_ships_the_eight_columns(m):
    out = m.embed_contract(_legacy(), {}, {})
    keys = set(_by_key(out["fields"]))
    assert keys == (
        {("document", n) for n in m.DEFAULT_DOC_FIELDS - {"supplier_name", "currency"}}
        | {("row", n) for n in m.DEFAULT_ROW_FIELDS - {"charge_type", "amount"}}
    )
    assert all(f["label_hint"] is None for f in out["fields"]), "no override, no supplier label"
    assert [c["header"] for c in out["output_columns"]] == [c["header"] for c in m.BUILTIN_STANDARD_COLUMNS]
    assert out["output_columns"][0]["source"] == "row.service_id"
    for key in m.LEGACY_KEYS:
        assert key not in out


def test_overrides_become_hints_on_the_pick_and_keep_catalogue_type_and_role(m):
    out = m.embed_contract(_legacy(field_overrides=[
        {"name": "invoice_number", "scope": "document", "type": "string", "role": "none",
         "label_hint": "Document No."},
        {"name": "invoice_date", "scope": "document", "type": "string", "role": "none",
         "label_hint": "Invoice Date", "date_format": "%d/%m/%Y"},
        {"name": "total_due", "scope": "document", "type": "string", "role": "none",
         "label_hint": "Invoice Total"},
    ]), {}, {})
    fields = _by_key(out["fields"])
    assert fields[("document", "invoice_number")]["role"] == "identifier"  # the base wins
    assert fields[("document", "invoice_number")]["label_hint"] == "Document No."
    assert fields[("document", "invoice_date")]["type"] == "date"
    assert fields[("document", "invoice_date")]["date_format"] == "%d/%m/%Y"
    assert fields[("document", "total_due")]["role"] == "total"
    assert fields[("document", "due_date")]["label_hint"] is None


def test_override_with_the_wrong_scope_resolves_by_unique_name(m):
    out = m.embed_contract(_legacy(field_overrides=[
        {"name": "account_number", "scope": "row", "label_hint": "Customer ID"},
    ]), {}, {})
    fields = _by_key(out["fields"])
    assert ("row", "account_number") not in fields
    assert fields[("document", "account_number")]["label_hint"] == "Customer ID"


def test_unknown_override_names_become_custom_fields_and_always_on_hints_are_kept(m):
    out = m.embed_contract(_legacy(field_overrides=[
        {"name": "total_account_level_charges", "scope": "document", "type": "currency",
         "role": "excluded_total", "label_hint": "Total Account Level Charges"},
        {"name": "supplier_name", "scope": "document", "label_hint": "LTM Limited", "required": True},
    ]), {}, {})
    fields = _by_key(out["fields"])
    custom = fields[("document", "total_account_level_charges")]
    assert custom["role"] == "excluded_total" and custom["type"] == "currency"
    assert fields[("document", "supplier_name")]["label_hint"] == "LTM Limited"
    assert ("document", "output_type") not in fields


def test_mapping_overrides_apply_only_when_unambiguous_and_paths_are_normalised(m):
    spec = {"spec_id": "x", "columns": [
        {"header": "DATE", "source": "header.invoice_date"},
        {"header": "DUP", "source": "line_item.amount"},
        {"header": "DUP", "source": "line_item.amount"},
        {"header": "TOTAL", "source": "total_due"},
    ]}
    out = m.embed_contract(_legacy(output_spec_id="x", output_mapping_overrides=[
        {"output_header": "DATE", "source": "row.billing_period_start", "fallback": "field.invoice_date",
         "transforms": ["trim"]},
        {"output_header": "DUP", "source": "row.quantity"},
    ]), {}, {"x": spec})
    columns = {c["header"]: c for c in out["output_columns"]}
    assert columns["DATE"]["source"] == "row.billing_period_start"
    assert columns["DATE"]["fallback"] == "field.invoice_date"
    assert columns["DATE"]["transforms"] == ["trim"]
    assert [c["source"] for c in out["output_columns"] if c["header"] == "DUP"] == ["row.amount", "row.amount"]
    assert columns["TOTAL"]["source"] == "field.total_due"
    # Column sources widen the field list; the overridden date source is read too.
    keys = set(_by_key(out["fields"]))
    assert ("row", "billing_period_start") in keys and ("row", "quantity") not in keys


def test_custom_schema_fields_are_embedded_whole(m):
    schema = {"schema_id": "s", "fields": [
        {"name": "document_id", "scope": "document", "type": "string", "role": "identifier", "required": True},
        {"name": "line_amount", "scope": "row", "type": "currency", "role": "amount", "required": True},
    ]}
    out = m.embed_contract(_legacy(field_schema_id="s"), {"s": schema}, {})
    fields = _by_key(out["fields"])
    assert fields[("document", "document_id")]["role"] == "identifier"
    assert fields[("row", "line_amount")]["role"] == "amount"
    assert ("document", "invoice_number") not in fields  # not in that schema


def test_embed_is_idempotent_and_leaves_new_profiles_alone(m):
    once = m.embed_contract(_legacy(), {}, {})
    assert m.embed_contract(once, {}, {}) == once
    fresh = {"profile_id": "n", "identity": {"canonical_name": "N"}, "fields": [{"name": "x", "scope": "row"}],
             "output_columns": []}
    assert m.embed_contract(fresh, {}, {}) == fresh


def test_downgrade_round_trip_keeps_hints_and_standard_mappings(m):
    embedded = m.embed_contract(_legacy(
        field_overrides=[{"name": "invoice_number", "scope": "document", "label_hint": "Doc"}],
        output_mapping_overrides=[{"output_header": "EXT_DATE", "source": "row.billing_period_start"}],
    ), {}, {})
    back = m.unembed_contract(embedded)
    assert back["output_spec_id"] == "standard.8col"
    assert [o["name"] for o in back["field_overrides"]] == ["invoice_number"]
    assert back["output_mapping_overrides"] == [
        {"output_header": "EXT_DATE", "source": "row.billing_period_start", "fallback": None, "transforms": []},
    ]
    assert m.embed_contract(back, {}, {})["output_columns"] == embedded["output_columns"]


def test_committed_profile_fixtures_are_embedded():
    """The guard: every profile JSON in the repo has been through the script."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "embed_profile_contract.py"), "--check"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_upgrade_against_sqlite_rewrites_rows_and_drops_the_registries(tmp_path, m):
    """Run the real upgrade() on a SQLite file prepared in the 023 shape."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, text

    engine = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE supplier_profiles (profile_id VARCHAR(128) PRIMARY KEY, data JSON)"))
        conn.execute(text(
            "CREATE TABLE field_schemas (schema_id VARCHAR(128) PRIMARY KEY, name VARCHAR(256), data JSON)"
        ))
        conn.execute(text(
            "CREATE TABLE output_specs (spec_id VARCHAR(128) PRIMARY KEY, name VARCHAR(256), data JSON)"
        ))
        conn.execute(text(
            "CREATE TABLE profile_authoring_sessions (id VARCHAR(36) PRIMARY KEY, "
            "output_spec_id VARCHAR(128) NOT NULL DEFAULT 'standard.8col', "
            "field_schema_id VARCHAR(128) NOT NULL DEFAULT 'invoice.standard', phase VARCHAR(32))"
        ))
        conn.execute(text("INSERT INTO output_specs VALUES ('two', 'Two', :d)"), {"d": json.dumps({
            "spec_id": "two", "columns": [{"header": "ID", "source": "row.service_id"},
                                          {"header": "AMT", "source": "row.amount"}],
        })})
        conn.execute(text("INSERT INTO supplier_profiles VALUES ('p', :d)"), {"d": json.dumps(
            _legacy(profile_id="p", output_spec_id="two")
        )})
        conn.execute(text("INSERT INTO profile_authoring_sessions (id, phase) VALUES ('s', 'setup')"))

    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            m.upgrade()

    with engine.connect() as conn:
        tables = {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
        assert "output_specs" not in tables and "field_schemas" not in tables
        columns = {r[1] for r in conn.execute(text("PRAGMA table_info(profile_authoring_sessions)"))}
        assert "output_spec_id" not in columns and "field_schema_id" not in columns
        data = json.loads(conn.execute(text("SELECT data FROM supplier_profiles WHERE profile_id='p'")).scalar())
    assert [c["header"] for c in data["output_columns"]] == ["ID", "AMT"]
    assert "output_spec_id" not in data
    assert ("row", "service_id") in set(_by_key(data["fields"]))
