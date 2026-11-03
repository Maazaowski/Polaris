"""provenance.json: where on the PDF each delivered cell was read from.

The deliverable is a table the operator cannot audit without opening the
PDF. This file joins the two: for every delivered row (in the exact order the
XLSX has them) the page, the printed row id(s) and, on the template path, a
normalized 0-1000 box per field; for header fields and totals the label and
value boxes. The invoice page draws these over the reconstructed page.

Template path: the interpreter captures boxes while it executes the rules
(``models/interpreter.py``) and parks them on the document's private
``_provenance`` slot. AI path: the extraction cites the printed row it read
each item from (``source_row_id``) and the page, so rows can still be
highlighted by id; that is marked ``approximate`` because no per-field boxes
exist. When nothing at all is known the file is not written.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from polaris.output.xlsx_writer import service_line_items
from polaris.validation.schema import CanonicalInvoice, ExtractedDocument

PROVENANCE_VERSION = 1


def build_provenance(invoice: ExtractedDocument) -> dict[str, Any] | None:
    """Assemble the provenance package for an extracted document, or None."""
    captured = getattr(invoice, "_provenance", None)
    if not isinstance(invoice, CanonicalInvoice):
        try:
            invoice = CanonicalInvoice.model_validate(invoice.model_dump(mode="python"))
        except Exception:  # pragma: no cover - defensive: an unparseable document has no rows to map
            return None
    items = service_line_items(invoice)

    by_row: dict[str, dict] = {}
    if captured:
        by_row = {e["source_row_id"]: e for e in captured.get("items", []) if e.get("source_row_id")}

    rows: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        entry = by_row.get(item.source_row_id or "")
        if entry is not None:
            rows.append({
                "row_index": index,
                "line_number": item.line_number,
                "page": entry.get("page") or item.source_page,
                "row_ids": list(entry.get("row_ids") or []),
                "box": entry.get("box"),
                "fields": dict(entry.get("fields") or {}),
            })
        else:
            rows.append({
                "row_index": index,
                "line_number": item.line_number,
                "page": item.source_page,
                "row_ids": [item.source_row_id] if item.source_row_id else [],
                "box": None,
                "fields": {},
            })

    header = dict(captured.get("header") or {}) if captured else {}
    totals = dict(captured.get("totals") or {}) if captured else {}
    known = any(r["page"] or r["row_ids"] for r in rows) or header or totals
    if not known:
        return None

    pages = sorted({
        int(p) for p in (
            [r["page"] for r in rows]
            + [h.get("page") for h in header.values()]
            + [t.get("page") for t in totals.values()]
        ) if p
    })
    return {
        "version": PROVENANCE_VERSION,
        "extraction_path": str(invoice.metadata.extraction_path),
        "model_id": invoice.metadata.model_id,
        # Exact per-field boxes only come from the interpreter; everything else
        # is "the printed row we read it from" at best.
        "approximate": captured is None,
        "pages": pages,
        "header": header,
        "totals": totals,
        "rows": rows,
    }


def write_provenance(invoice: ExtractedDocument, output_path: Path) -> Path | None:
    """Write provenance.json next to the deliverable; None when nothing is known."""
    package = build_provenance(invoice)
    if package is None:
        return None
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(package, indent=2, default=str), encoding="utf-8")
    return output_path
