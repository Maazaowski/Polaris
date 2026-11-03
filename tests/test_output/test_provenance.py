"""provenance.json: every delivered row points back at the page it was read from.

Runs the committed corpus models through the interpreter (no AI) and checks
the provenance package lines up with the delivered rows, carries boxes in the
canvas's 0-1000 space, and degrades to "approximate" on the AI path.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from stencil.models.interpreter import execute_model
from stencil.models.schema import ExtractionModel
from stencil.output.provenance import build_provenance, write_provenance
from stencil.output.xlsx_writer import build_output_rows
from stencil.validation.schema import (
    CanonicalInvoice,
    ExtractionMetadata,
    ExtractionPath,
    InvoiceHeader,
    LineItem,
)

CORPUS = Path(__file__).resolve().parents[1] / "fixtures" / "corpus"
LAYOUTS = [
    ("colt.standard", "756260789_20251001.pdf"),  # layout-grouping strategy
    ("eunetworks.standard", "A837737 - IE-SI53564.pdf"),  # rule engine with column bands
]


def _run(layout: str, pdf: str) -> CanonicalInvoice:
    model = ExtractionModel.model_validate(json.loads((CORPUS / layout / "model.json").read_text(encoding="utf-8")))
    return execute_model(model, CORPUS / layout / "invoices" / pdf, intake_id="prov-test")


def _in_page_space(box: dict) -> bool:
    in_range = all(0 <= box[k] <= 1000 for k in ("x0", "y0", "x1", "y1"))
    return in_range and box["x0"] <= box["x1"] and box["y0"] <= box["y1"]


@pytest.mark.parametrize(("layout", "pdf"), LAYOUTS, ids=[layout for layout, _ in LAYOUTS])
def test_every_delivered_row_is_located(layout, pdf):
    invoice = _run(layout, pdf)
    package = build_provenance(invoice)

    assert package is not None and package["approximate"] is False
    assert package["extraction_path"] == "model"
    delivered = build_output_rows(invoice)
    assert [r["row_index"] for r in package["rows"]] == list(range(len(delivered)))
    for row in package["rows"]:
        assert row["page"] and row["row_ids"], row
        assert row["box"] is not None and _in_page_space(row["box"]), row
    referenced = (
        {r["page"] for r in package["rows"]}
        | {h["page"] for h in package["header"].values()}
        | {t["page"] for t in package["totals"].values()}
    )
    assert package["pages"] == sorted(referenced)


def test_header_fields_have_label_and_value_boxes():
    invoice = _run(*LAYOUTS[0])
    package = build_provenance(invoice)

    located = package["header"]
    assert {"invoice_number", "invoice_date", "account_number"} <= set(located)
    for name, entry in located.items():
        assert entry["page"] >= 1, name
        assert entry["value_box"] is not None and _in_page_space(entry["value_box"]), name
        assert entry["label_box"] is not None and _in_page_space(entry["label_box"]), name
    assert "total_due" in package["totals"]


def test_rule_engine_items_carry_per_field_boxes():
    invoice = _run(*LAYOUTS[1])
    package = build_provenance(invoice)

    first = package["rows"][0]
    assert {"service_id", "amount"} <= set(first["fields"])
    for name, field in first["fields"].items():
        assert field["page"] == first["page"], name
        assert _in_page_space(field["box"]), name
    # A column-band field is narrower than the whole row.
    amount = first["fields"]["amount"]["box"]
    assert amount["x1"] - amount["x0"] < first["box"]["x1"] - first["box"]["x0"]


def _ai_invoice(**item_kwargs) -> CanonicalInvoice:
    return CanonicalInvoice(
        intake_id="ai-1",
        header=InvoiceHeader(supplier_name="Acme", invoice_number="1", invoice_date="2026-01-01"),
        line_items=[LineItem(line_number=1, description="Svc", service_id="S1", amount=Decimal("10"), **item_kwargs)],
        metadata=ExtractionMetadata(extraction_path=ExtractionPath.AI),
    )


def test_ai_path_is_approximate_and_cites_the_printed_row():
    package = build_provenance(_ai_invoice(source_page=3, source_row_id="p3.r7"))

    assert package is not None and package["approximate"] is True
    assert package["rows"] == [{
        "row_index": 0, "line_number": 1, "page": 3, "row_ids": ["p3.r7"], "box": None, "fields": {},
    }]
    assert package["header"] == {} and package["pages"] == [3]


def test_nothing_known_means_no_file(tmp_path):
    assert build_provenance(_ai_invoice()) is None
    assert write_provenance(_ai_invoice(), tmp_path / "provenance.json") is None
    assert not (tmp_path / "provenance.json").exists()


def test_write_provenance_round_trips(tmp_path):
    invoice = _run(*LAYOUTS[0])
    path = write_provenance(invoice, tmp_path / "provenance.json")

    assert path is not None
    assert json.loads(path.read_text(encoding="utf-8"))["rows"][0]["row_ids"]
