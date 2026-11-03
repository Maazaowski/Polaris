```json
{
  "ts": "2026-11-03T15:01:39.581+00:00",
  "call_type": "model_authoring",
  "context": "X:scalars",
  "model": "gpt-5.5",
  "max_tokens": 32768,
  "finish_reason": null,
  "tokens_input": 10,
  "tokens_output": 5,
  "est_cost_usd": 0.0002,
  "duration_ms": 0,
  "status": "success",
  "error": null
}
```

# AI call: model_authoring

## System
You are an expert at writing REUSABLE, DETERMINISTIC, declarative extraction rule documents for
invoices. A generic interpreter (no AI, no supplier knowledge) will replay your rule document on
future invoices of the same layout, so EVERY piece of layout knowledge must live in the rules.

You are given (1) coordinate-aware visual rows/cells from one invoice (each cell has a normalized
x range 0-1000 of the page width), (2) the exact ground-truth values already extracted from it,
and (3) evidence pinning each ground-truth value to its page/row/cell.

Write the rule document:

1. header_fields — label-relative locators per header field (label text, value_position,
   optional date_format as printed ON THE PAGE, optional value_pattern with one capture group,
   occurrence, page).

2. region — start_anchors / end_anchors (text printed on the page that opens/closes the
   line-item section) and columns: named vertical bands with normalized x0/x1 (0-1000) — copy
   them from the x spans shown on the cells (already normalized to 0-1000 of page width),
   widened slightly. Choose stable bands that will hold when row counts change.
   end_scope: 'document' when the end anchor truly ends the section (default); 'page' ONLY when
   the end anchor is a per-page footer (e.g. 'carried forward') and items resume on the next page.

3. row_classifiers — ordered patterns that classify each region row by ROLE. You define the
   roles. Examples: an 'item_start' row is one whose first column matches an identifier pattern;
   an 'item_total' row starts with 'Total'; noise rows get role 'skip'. Patterns must describe
   the SHAPE of rows (regex on row text or on a named column's cell), never literal IDs or
   amounts from this invoice. Unmatched rows automatically get role 'detail'.

4. grouping — how classified rows become logical line items:
   - 'single_row' + item_role: each matching row is one item.
   - 'span' + start_role/end_role: a group runs from a start row to a closing row.
   - 'role_transition' + start_role: a new group begins at each start row.
   emit='one_item_per_group' produces one item per group; emit='one_item_per_role_row' +
   emit_role produces one item per matching row inside the group (shared context from the group).

5. item_fields — one rule per canonical field (service_id, billing_reference, description,
   charge_type, amount, tax_amount, currency, billing_period_start, billing_period_end, quantity,
   unit_rate). Each rule selects rows (by role / first / last / emit_row / all_in_group), reads a
   column band or applies a regex with ONE capture group, then transforms (currency, date with
   strptime format, integer, value_map for charge_type). Use same_as to copy another field,
   literal for constants. Only 'amount' may be marked required — auxiliary fields (billing
   periods, quantity, unit_rate, ...) can be absent on one-off items even when every item on
   THIS invoice has them; items missing them must still be emitted.

6. totals — label-relative locators for subtotal, tax, fees, total_due, tax_rate, current_charges
   (only those actually printed).

7. self_checks — add {"check": "sum_of_items_equals", "field": ...} when the sum of item amounts
   should reconcile against a stated total.

CRITICAL RULES:
- Describe repeating patterns, never fixed row counts, literal IDs, or literal amounts.
- All regex must be valid Python regex; use exactly one capture group when extracting a value.
- Choose column x-ranges from the visible cell coordinates, widened slightly for tolerance.
- When ground-truth line items have no per-line tax_amount, line amounts are net (pre-tax) and
  invoice-level VAT/tax belongs in totals/tax_rate, NOT duplicated in item rows.
- When line amounts are net, sum_of_items_equals must target subtotal or current_charges — NOT
  total_due (total_due includes tax).
- When ground-truth line items include per-line tax_amount, extract those amounts per item.
- Always extract invoice tax_rate when the invoice states a rate, even when per-line tax is absent.
- If ground truth header.currency is set but no dedicated 'Currency' label appears in the layout text,
  use a literal value for currency — do NOT anchor currency to unrelated labels like 'Bank Name'.
- Multi-row service blocks must be grouped with span/role_transition grouping. Use the supplier
  hints and evidence to decide which identifiers are service_id vs billing_reference; do not assume
  a universal ID format.
- Group-total layouts: when the ground truth has one line item per logical service/group but the
  page shows many detail rows followed by a total/subtotal row, do not emit one item per detail row.
  Match the ground-truth item COUNT exactly by emitting at the same granularity shown in the
  examples and evidence.
- If your first attempt produces too MANY rows, you are almost certainly emitting one item per detail
  row instead of one per group — switch to group emission. If you produce ZERO rows, your start_anchors
  or row_classifier patterns don't match the page; widen them using the anchors/markers in the hints.
- Supplier hints are advisory context; the executable rules must stand on their own.
- The rule document must reproduce the ground-truth values EXACTLY on this invoice.

## User
Write a reusable declarative extraction rule document for this supplier layout.
FOCUS: author ONLY the document-level locators — header_fields and totals (plus any self_checks). Do NOT author line-item rules.

Tax handling for this invoice: Line amounts on this invoice are NET (pre-tax); extract invoice tax_rate and put VAT in totals.
EXT_TAX delivery is profile-controlled; do not assume blank row tax is automatically calculated.

--- INSTRUCTION PRECEDENCE ---
1. Invoice-visible evidence always wins; surface ambiguity via warnings/exceptions.
2. Structured profile fields below are executable rules and are authoritative.
3. Free-text notes are supplemental guidance only. Where a note contradicts a
   structured field, follow the structured field.
4. A note beginning 'override:' is authoritative and supersedes the field it names.

Known document field labels for this source (hints):
  - invoice_number: 'Invoice Number'
  - invoice_date: 'Invoice Date'
  - due_date: 'Due Date'
  - account_number: 'Account Number'
  - total_due: 'Total Due'

--- GROUND TRUTH VALUES (the rules must reproduce these exactly on this invoice) ---
{
  "header": {
    "invoice_number": "INV1",
    "invoice_date": "2026-01-01",
    "due_date": null,
    "account_number": "A1",
    "ban": null,
    "currency": "USD"
  },
  "totals": {
    "subtotal": null,
    "tax": null,
    "fees": null,
    "total_due": null,
    "tax_rate": null,
    "current_charges": null
  },
  "line_items": []
}

--- EVIDENCE: where each ground-truth value sits in the layout ---
{
  "target_alignment": {
    "header": {},
    "totals": {}
  }
}

--- COORDINATE-AWARE INVOICE LAYOUT (each cell shows its x range) ---

=== PAGE 1 ===
LAYOUT PAGE 1

## JSON schema requested
```json
{
  "name": "extraction_rules_scalars",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "header_fields": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "name": {
              "type": "string",
              "enum": [
                "invoice_number",
                "invoice_date",
                "due_date",
                "account_number",
                "ban",
                "billing_period_start",
                "billing_period_end",
                "currency",
                "po_number"
              ]
            },
            "label": {
              "type": "string"
            },
            "value_position": {
              "type": "string",
              "enum": [
                "right",
                "left",
                "below",
                "above"
              ]
            },
            "value_pattern": {
              "type": [
                "string",
                "null"
              ]
            },
            "date_format": {
              "type": [
                "string",
                "null"
              ]
            },
            "ignore_percent": {
              "type": "boolean"
            },
            "occurrence": {
              "type": "string",
              "enum": [
                "first",
                "last"
              ]
            },
            "page": {
              "type": "integer"
            },
            "required": {
              "type": "boolean"
            }
          },
          "required": [
            "name",
            "label",
            "value_position",
            "value_pattern",
            "date_format",
            "ignore_percent",
            "occurrence",
            "page",
            "required"
          ],
          "additionalProperties": false
        }
      },
      "totals": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "name": {
              "type": "string",
              "enum": [
                "subtotal",
                "tax",
                "fees",
                "current_charges",
                "total_due",
                "tax_rate"
              ]
            },
            "label": {
              "type": "string"
            },
            "value_position": {
              "type": "string",
              "enum": [
                "right",
                "left",
                "below",
                "above"
              ]
            },
            "value_pattern": {
              "type": [
                "string",
                "null"
              ]
            },
            "date_format": {
              "type": [
                "string",
                "null"
              ]
            },
            "ignore_percent": {
              "type": "boolean"
            },
            "occurrence": {
              "type": "string",
              "enum": [
                "first",
                "last"
              ]
            },
            "page": {
              "type": "integer"
            },
            "required": {
              "type": "boolean"
            }
          },
          "required": [
            "name",
            "label",
            "value_position",
            "value_pattern",
            "date_format",
            "ignore_percent",
            "occurrence",
            "page",
            "required"
          ],
          "additionalProperties": false
        }
      },
      "self_checks": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "check": {
              "type": "string",
              "enum": [
                "sum_of_items_equals"
              ]
            },
            "field": {
              "type": "string",
              "enum": [
                "subtotal",
                "current_charges",
                "total_due"
              ]
            },
            "tolerance": {
              "type": "number"
            }
          },
          "required": [
            "check",
            "field",
            "tolerance"
          ],
          "additionalProperties": false
        }
      },
      "confidence": {
        "type": "number"
      },
      "notes": {
        "type": [
          "string",
          "null"
        ]
      }
    },
    "required": [
      "header_fields",
      "totals",
      "self_checks",
      "confidence",
      "notes"
    ],
    "additionalProperties": false
  }
}
```

## Response
```
{"header_fields": [], "totals": [], "self_checks": [], "confidence": 0.9, "notes": null}
```
