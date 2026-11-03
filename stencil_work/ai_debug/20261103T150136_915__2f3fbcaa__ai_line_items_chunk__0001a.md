```json
{
  "ts": "2026-11-03T15:01:36.915+00:00",
  "call_type": "ai_line_items_chunk",
  "context": "0001a",
  "model": "gpt-5.5",
  "max_tokens": 32768,
  "finish_reason": "stop",
  "tokens_input": 10,
  "tokens_output": 5,
  "est_cost_usd": 0.0002,
  "duration_ms": 0,
  "status": "success",
  "error": null
}
```

# AI call: ai_line_items_chunk

## System
You are a precise invoice data extractor. Respond only with JSON matching the supplied schema.
The JSON uses compact aliases to minimize output tokens. Do not include explanations.
Use exact values from coordinate-aware rows. Use null when a field is unavailable.


## User
Extract only compact delivered output line items from this bounded layout chunk.
Output type: standard
Return only rows that should appear in the delivered output workbook.
Do not emit MRC, fee, surcharge, tax, subtotal, total, header, footer, duplicate, or noise rows as separate rows when the profile says the delivered output is grouped.
For grouped output, emit one row per logical service/group. Put the selected group/current-charge/subtotal amount in row.a and put grouped tax in row.x only when the source prints per-group tax.
Classify row.c as recurring, one_time, tax, fee, credit, adjustment, surcharge, usage, or unknown. Use recurring for grouped service output rows unless another type is clearly printed.
For each emitted row, set row.r to the best source row id for the delivered amount row, exactly as printed (for example p3.r12).
Use null for unavailable fields. Amount fields must be numeric with no currency symbols.
Compact row aliases:
- row.r: _row_ref
- row.s: service_id
- row.b: billing_reference
- row.c: charge_type
- row.a: amount
- row.x: tax_amount
- row.p: source_page

--- CHUNK 0001a LAYOUT ROWS ---
=== PAGE 1 ===
p1.r1 ACCOUNT 1 NAME Row 1 10.00
p1.r2 ACCOUNT 2 NAME Row 2 10.00

## JSON schema requested
```json
{
  "name": "compact_invoice_line_items",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "rows": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "r": {
              "type": "string",
              "pattern": "^p\\d+\\.r\\d+(?:\\D.*)?$"
            },
            "s": {
              "type": [
                "string",
                "null"
              ]
            },
            "b": {
              "type": [
                "string",
                "null"
              ]
            },
            "c": {
              "type": [
                "string",
                "null"
              ],
              "enum": [
                "recurring",
                "one_time",
                "tax",
                "fee",
                "credit",
                "adjustment",
                "surcharge",
                "usage",
                "unknown",
                null
              ]
            },
            "a": {
              "type": [
                "number",
                "null"
              ]
            },
            "x": {
              "type": [
                "number",
                "null"
              ]
            },
            "p": {
              "type": [
                "integer",
                "null"
              ]
            }
          },
          "required": [
            "r",
            "s",
            "b",
            "c",
            "a",
            "x",
            "p"
          ],
          "additionalProperties": false
        }
      }
    },
    "required": [
      "rows"
    ],
    "additionalProperties": false
  }
}
```

## Response
```
{"rows": [{"r": "p1.r1", "s": "A", "b": "Name A", "a": 10, "x": 1, "p": 1}]}
```
