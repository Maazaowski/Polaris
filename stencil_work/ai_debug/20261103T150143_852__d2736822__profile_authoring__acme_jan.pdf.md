```json
{
  "ts": "2026-11-03T15:01:43.851+00:00",
  "call_type": "profile_authoring",
  "context": "acme_jan.pdf",
  "model": "gpt-5.5",
  "max_tokens": 32768,
  "finish_reason": null,
  "tokens_input": 100,
  "tokens_output": 40,
  "est_cost_usd": 0.0017,
  "duration_ms": 0,
  "status": "success",
  "error": null
}
```

# AI call: profile_authoring

## System
You are an extraction-onboarding assistant for Polaris.

You configure a SupplierProfile: a small JSON config that tells the system how to
read ONE supplier's invoice layout and deliver the customer's required columns.
You are given, for each sample invoice: the coordinate-aware PDF text and a
baseline AI extraction. The baseline is evidence, not guaranteed ground truth.
You may also be given the user's guidance, an XLS/XLSX blueprint per invoice,
and the diff between the current draft's preview and that blueprint.

Your job each turn:
1. Read the layouts and the user's guidance.
2. Build an internal extraction plan before choosing profile fields. The plan
   must decide supplier/document type, requested output layout, header labels,
   invoice totals, line-item section boundaries, row granularity, service ID source,
   billing reference source, amount source, tax source, page-break
   carry-forward rules, skip rules, reconciliation targets, and unresolved risks.
3. Produce the BEST SupplierProfile draft you can, conforming exactly to the
   provided JSON schema. Only set fields you have real evidence for; leave the
   rest at their defaults (empty string / empty list / null).
4. Write a short, plain-language assistant_message explaining the extraction
   plan decisions you encoded in the draft, what changed, and why. Describe every
   output mapping change by output header, source, fallback, and reason. Ask one
   focused question when mapping evidence is ambiguous.

Guidance on the load-bearing fields:
- identity.canonical_name + aliases: the supplier's name and the variants printed
  on documents.
- field_overrides: how an existing canonical extraction field is recognized on
  THIS supplier's invoice. field_path identifies the exact document or row field;
  label_hint is its printed label. For dates, encode an explicitly stated input
  format such as %d/%m/%Y in date_format; delivery is normalized to %m/%d/%Y.
  Never relabel field.invoice_date as "Billing Period Start" to simulate delivery.
- output_mapping_overrides: exceptions to the selected OutputSpec. They decide
  which already-extracted canonical value populates a delivered output column.
  A field.* source repeats one document value; a row.* source resolves separately
  for every delivered line. Use this for EXT_DATE -> row.billing_period_start.
- transforms are safe delivery normalizations applied after source/fallback.
  Use digits_only for requests such as "remove dashes from account number";
  never claim a requested transform is implemented only by mentioning it in notes.
- Only create an output mapping when the user explicitly requests it or blueprint
  values consistently match the same alternative field across samples. Mixed or
  weak evidence requires an open question and no speculative mapping.
- Return the COMPLETE desired output_mapping_overrides list every turn. Preserve
  existing mappings unless the user requests a reset/change or strong new evidence
  contradicts them. Omitting an existing mapping resets it to the OutputSpec.
- line_item_hints.line_item_granularity: per_charge_row (one row per charge),
  per_service_group, or per_total_group (one row per service/total block).
- service_id_preference / billing_reference_preference: which printed identifier
  becomes the delivered service id and billing reference.
- When customer identifiers, supplier-internal references, account/sub-account
  numbers, or invoice numbers share the same shape, never use an unqualified
  broad regex. Encode the printed label/context that distinguishes the customer
  identifier or ask one focused question.
- *_column_label: the printed column header for the service id, billing reference,
  amount, or tax amount.
- amount_source / tax_source / tax_output_mode / tax_rate_source: executable
  amount and tax policies used when the blueprint shows how amounts and taxes
  should be delivered.
- detail_start_marker: the text where the line-item section begins.
- skip_row_keywords: text on rows that must NOT become line items (e.g. running totals).
- notes: free-text guidance for the AI extractor about this layout.

Use the available extraction toolkit: classify the document, read header fields,
fingerprint layout anchors, learn from XLS/XLSX blueprint rows, plan extraction
strategy, preserve parent-child blocks across pages, resolve grouped rows,
choose tax behavior, reconcile against invoice totals, diff against the
blueprint, explain differences, and route unresolved risks to review.

Use attached XLS/XLSX rows as the delivery contract for columns, row structure,
and mapping semantics. Use the PDF as evidence for printed facts and totals. A
difference is evidence to investigate, not proof that either side is wrong. Do
not drop invoice-backed charges only because they are absent from the blueprint;
explain exclusions or unresolved differences. Use the blueprint to learn what to
deliver and the PDF to prove what was printed. Explain every meaningful difference.

When discovery_candidates is present, select only a supplied candidate_id. Set
selected_plan_id to null when the deterministic evidence is insufficient and
state the exact ambiguity; never invent executable formulas or regexes.

## User
{
  "field_schema": {
    "schema_id": "invoice.standard",
    "fields": [
      {
        "name": "output_type",
        "scope": "document",
        "type": "string",
        "role": "none",
        "label_hint": null,
        "date_format": null
      },
      {
        "name": "supplier_name",
        "scope": "document",
        "type": "string",
        "role": "none",
        "label_hint": null,
        "date_format": null
      },
      {
        "name": "supplier_aliases",
        "scope": "document",
        "type": "string",
        "role": "none",
        "label_hint": null,
        "date_format": null
      },
      {
        "name": "invoice_number",
        "scope": "document",
        "type": "string",
        "role": "identifier",
        "label_hint": "Invoice Number",
        "date_format": null
      },
      {
        "name": "invoice_date",
        "scope": "document",
        "type": "date",
        "role": "none",
        "label_hint": "Invoice Date",
        "date_format": null
      },
      {
        "name": "due_date",
        "scope": "document",
        "type": "date",
        "role": "none",
        "label_hint": "Due Date",
        "date_format": null
      },
      {
        "name": "account_number",
        "scope": "document",
        "type": "string",
        "role": "none",
        "label_hint": "Account Number",
        "date_format": null
      },
      {
        "name": "ban",
        "scope": "document",
        "type": "string",
        "role": "none",
        "label_hint": null,
        "date_format": null
      },
      {
        "name": "billing_period_start",
        "scope": "document",
        "type": "date",
        "role": "none",
        "label_hint": null,
        "date_format": null
      },
      {
        "name": "billing_period_end",
        "scope": "document",
        "type": "date",
        "role": "none",
        "label_hint": null,
        "date_format": null
      },
      {
        "name": "currency",
        "scope": "document",
        "type": "string",
        "role": "none",
        "label_hint": null,
        "date_format": null
      },
      {
        "name": "po_number",
        "scope": "document",
        "type": "string",
        "role": "none",
        "label_hint": null,
        "date_format": null
      },
      {
        "name": "payment_terms",
        "scope": "document",
        "type": "string",
        "role": "none",
        "label_hint": null,
        "date_format": null
      },
      {
        "name": "source_page",
        "scope": "document",
        "type": "integer",
        "role": "none",
        "label_hint": null,
        "date_format": null
      },
      {
        "name": "confidence",
        "scope": "document",
        "type": "number",
        "role": "none",
        "label_hint": null,
        "date_format": null
      },
      {
        "name": "subtotal",
        "scope": "document",
        "type": "currency",
        "role": "subtotal",
        "label_hint": null,
        "date_format": null
      },
      {
        "name": "tax",
        "scope": "document",
        "type": "currency",
        "role": "tax",
        "label_hint": null,
        "date_format": null
      },
      {
        "name": "fees",
        "scope": "document",
        "type": "currency",
        "role": "none",
        "label_hint": null,
        "date_format": null
      },
      {
        "name": "current_charges",
        "scope": "document",
        "type": "currency",
        "role": "subtotal",
        "label_hint": null,
        "date_format": null
      },
      {
        "name": "total_due",
        "scope": "document",
        "type": "currency",
        "role": "total",
        "label_hint": "Total Due",
        "date_format": null
      },
      {
        "name": "tax_rate",
        "scope": "document",
        "type": "number",
        "role": "tax_rate",
        "label_hint": null,
        "date_format": null
      },
      {
        "name": "line_number",
        "scope": "row",
        "type": "integer",
        "role": "none",
        "label_hint": null,
        "date_format": null
      },
      {
        "name": "service_id",
        "scope": "row",
        "type": "string",
        "role": "identifier",
        "label_hint": null,
        "date_format": null
      },
      {
        "name": "billing_reference",
        "scope": "row",
        "type": "string",
        "role": "identifier",
        "label_hint": null,
        "date_format": null
      },
      {
        "name": "description",
        "scope": "row",
        "type": "string",
        "role": "none",
        "label_hint": null,
        "date_format": null
      },
      {
        "name": "charge_type",
        "scope": "row",
        "type": "enum",
        "role": "none",
        "label_hint": null,
        "date_format": null
      },
      {
        "name": "amount",
        "scope": "row",
        "type": "currency",
        "role": "amount",
        "label_hint": null,
        "date_format": null
      },
      {
        "name": "tax_amount",
        "scope": "row",
        "type": "currency",
        "role": "tax",
        "label_hint": null,
        "date_format": null
      },
      {
        "name": "currency",
        "scope": "row",
        "type": "string",
        "role": "none",
        "label_hint": null,
        "date_format": null
      },
      {
        "name": "billing_period_start",
        "scope": "row",
        "type": "date",
        "role": "none",
        "label_hint": null,
        "date_format": null
      },
      {
        "name": "billing_period_end",
        "scope": "row",
        "type": "date",
        "role": "none",
        "label_hint": null,
        "date_format": null
      },
      {
        "name": "quantity",
        "scope": "row",
        "type": "number",
        "role": "none",
        "label_hint": null,
        "date_format": null
      },
      {
        "name": "unit_rate",
        "scope": "row",
        "type": "currency",
        "role": "none",
        "label_hint": null,
        "date_format": null
      },
      {
        "name": "source_page",
        "scope": "row",
        "type": "integer",
        "role": "none",
        "label_hint": null,
        "date_format": null
      },
      {
        "name": "confidence",
        "scope": "row",
        "type": "number",
        "role": "none",
        "label_hint": null,
        "date_format": null
      }
    ]
  },
  "deliverable_columns": [
    {
      "header": "EXT_SERVICEID",
      "source": "row.service_id",
      "fallback": "row.billing_reference"
    },
    {
      "header": "EXT_BILLINGREFERENCE",
      "source": "row.billing_reference",
      "fallback": "row.service_id"
    },
    {
      "header": "EXT_DATE",
      "source": "field.invoice_date",
      "fallback": null
    },
    {
      "header": "formula",
      "source": "field.due_date",
      "fallback": "field.invoice_date"
    },
    {
      "header": "EXT_AMOUNT",
      "source": "row.amount",
      "fallback": null
    },
    {
      "header": "EXT_ACCOUNT",
      "source": "field.account_number",
      "fallback": null
    },
    {
      "header": "EXT_INVOICENUMBER",
      "source": "field.invoice_number",
      "fallback": null
    },
    {
      "header": "EXT_TAX",
      "source": "computed.line_tax",
      "fallback": null
    }
  ],
  "allowed_output_sources": [
    "field.output_type",
    "field.supplier_name",
    "field.supplier_aliases",
    "field.invoice_number",
    "field.invoice_date",
    "field.due_date",
    "field.account_number",
    "field.ban",
    "field.billing_period_start",
    "field.billing_period_end",
    "field.currency",
    "field.po_number",
    "field.payment_terms",
    "field.source_page",
    "field.confidence",
    "field.subtotal",
    "field.tax",
    "field.fees",
    "field.current_charges",
    "field.total_due",
    "field.tax_rate",
    "row.line_number",
    "row.service_id",
    "row.billing_reference",
    "row.description",
    "row.charge_type",
    "row.amount",
    "row.tax_amount",
    "row.currency",
    "row.billing_period_start",
    "row.billing_period_end",
    "row.quantity",
    "row.unit_rate",
    "row.source_page",
    "row.confidence",
    "computed.line_tax"
  ],
  "conversation": [
    {
      "role": "user",
      "content": "Service ID is the leftmost number, one row per charge."
    }
  ],
  "current_draft": null,
  "discovery_candidates": null,
  "sample_invoices": [
    {
      "label": "acme_jan.pdf",
      "baseline_extracted_evidence": {
        "header": {
          "invoice_number": "INV1"
        },
        "totals": {
          "subtotal": "100.00",
          "tax": "8.25"
        },
        "line_items": [
          {
            "amount": "100.00",
            "tax_amount": "8.25"
          }
        ]
      },
      "invoice_totals": {
        "subtotal": "100.00",
        "tax": "8.25",
        "sampled_line_amount_total": "100.00",
        "sampled_line_tax_total": "8.25",
        "sampled_line_count": 1
      },
      "layout_text": [
        "[p1] Invoice ... Service Charges ..."
      ],
      "blueprint_context": {
        "filename": "acme_jan.xls",
        "sheet_name": "Invoice Data",
        "raw_headers": [
          "EXT_SERVICEID",
          "EXT_AMOUNT",
          "EXT_TAX"
        ],
        "aligned_rows": [
          [
            "SVC1",
            "",
            "",
            "",
            "100.00",
            "",
            "",
            "8.25"
          ]
        ],
        "row_count": 1,
        "sample_rows": [
          [
            "SVC1",
            "",
            "",
            "",
            "100.00",
            "",
            "",
            "8.25"
          ]
        ],
        "totals": {
          "amount": "100.00",
          "tax": "8.25"
        },
        "warnings": []
      },
      "blueprint_vs_invoice_summary": {
        "blueprint_row_count": 1,
        "invoice_line_item_count_in_prompt": 1,
        "blueprint_totals": {
          "amount": "100.00",
          "tax": "8.25"
        },
        "invoice_totals": {
          "subtotal": "100.00",
          "tax": "8.25"
        },
        "comparisons": [
          {
            "blueprint": "amount",
            "invoice": "subtotal",
            "blueprint_value": "100.00",
            "invoice_value": "100.00"
          },
          {
            "blueprint": "tax",
            "invoice": "tax",
            "blueprint_value": "8.25",
            "invoice_value": "8.25"
          }
        ],
        "output_mapping_evidence": [
          {
            "output_header": "EXT_SERVICEID",
            "base_source": "row.service_id",
            "blueprint_values": [
              "SVC1"
            ],
            "base_values": [],
            "base_matches": false,
            "matching_alternative_sources": []
          }
        ],
        "warnings": []
      },
      "preview_vs_blueprint_diff": "exact match"
    }
  ]
}

## JSON schema requested
```json
{
  "name": "supplier_profile_draft",
  "strict": true,
  "schema": {
    "type": "object",
    "properties": {
      "assistant_message": {
        "type": "string"
      },
      "open_questions": {
        "type": "array",
        "items": {
          "type": "string"
        }
      },
      "confidence": {
        "type": "number"
      },
      "selected_plan_id": {
        "type": [
          "string",
          "null"
        ],
        "enum": [
          "deterministic.v1",
          null
        ]
      },
      "profile": {
        "type": "object",
        "properties": {
          "canonical_name": {
            "type": "string"
          },
          "aliases": {
            "type": "array",
            "items": {
              "type": "string"
            }
          },
          "output_type": {
            "type": "string"
          },
          "notes": {
            "type": [
              "string",
              "null"
            ]
          },
          "field_overrides": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "field_path": {
                  "type": "string",
                  "enum": [
                    "field.output_type",
                    "field.supplier_name",
                    "field.supplier_aliases",
                    "field.invoice_number",
                    "field.invoice_date",
                    "field.due_date",
                    "field.account_number",
                    "field.ban",
                    "field.billing_period_start",
                    "field.billing_period_end",
                    "field.currency",
                    "field.po_number",
                    "field.payment_terms",
                    "field.source_page",
                    "field.confidence",
                    "field.subtotal",
                    "field.tax",
                    "field.fees",
                    "field.current_charges",
                    "field.total_due",
                    "field.tax_rate",
                    "row.line_number",
                    "row.service_id",
                    "row.billing_reference",
                    "row.description",
                    "row.charge_type",
                    "row.amount",
                    "row.tax_amount",
                    "row.currency",
                    "row.billing_period_start",
                    "row.billing_period_end",
                    "row.quantity",
                    "row.unit_rate",
                    "row.source_page",
                    "row.confidence"
                  ]
                },
                "label_hint": {
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
                }
              },
              "required": [
                "field_path",
                "label_hint",
                "date_format"
              ],
              "additionalProperties": false
            }
          },
          "output_mapping_overrides": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "output_header": {
                  "type": "string",
                  "enum": [
                    "EXT_SERVICEID",
                    "EXT_BILLINGREFERENCE",
                    "EXT_DATE",
                    "formula",
                    "EXT_AMOUNT",
                    "EXT_ACCOUNT",
                    "EXT_INVOICENUMBER",
                    "EXT_TAX"
                  ]
                },
                "source": {
                  "type": "string",
                  "enum": [
                    "field.output_type",
                    "field.supplier_name",
                    "field.supplier_aliases",
                    "field.invoice_number",
                    "field.invoice_date",
                    "field.due_date",
                    "field.account_number",
                    "field.ban",
                    "field.billing_period_start",
                    "field.billing_period_end",
                    "field.currency",
                    "field.po_number",
                    "field.payment_terms",
                    "field.source_page",
                    "field.confidence",
                    "field.subtotal",
                    "field.tax",
                    "field.fees",
                    "field.current_charges",
                    "field.total_due",
                    "field.tax_rate",
                    "row.line_number",
                    "row.service_id",
                    "row.billing_reference",
                    "row.description",
                    "row.charge_type",
                    "row.amount",
                    "row.tax_amount",
                    "row.currency",
                    "row.billing_period_start",
                    "row.billing_period_end",
                    "row.quantity",
                    "row.unit_rate",
                    "row.source_page",
                    "row.confidence",
                    "computed.line_tax"
                  ]
                },
                "fallback": {
                  "type": [
                    "string",
                    "null"
                  ],
                  "enum": [
                    "field.output_type",
                    "field.supplier_name",
                    "field.supplier_aliases",
                    "field.invoice_number",
                    "field.invoice_date",
                    "field.due_date",
                    "field.account_number",
                    "field.ban",
                    "field.billing_period_start",
                    "field.billing_period_end",
                    "field.currency",
                    "field.po_number",
                    "field.payment_terms",
                    "field.source_page",
                    "field.confidence",
                    "field.subtotal",
                    "field.tax",
                    "field.fees",
                    "field.current_charges",
                    "field.total_due",
                    "field.tax_rate",
                    "row.line_number",
                    "row.service_id",
                    "row.billing_reference",
                    "row.description",
                    "row.charge_type",
                    "row.amount",
                    "row.tax_amount",
                    "row.currency",
                    "row.billing_period_start",
                    "row.billing_period_end",
                    "row.quantity",
                    "row.unit_rate",
                    "row.source_page",
                    "row.confidence",
                    "computed.line_tax",
                    null
                  ]
                },
                "transforms": {
                  "type": "array",
                  "items": {
                    "type": "string",
                    "enum": [
                      "digits_only",
                      "trim",
                      "uppercase",
                      "lowercase"
                    ]
                  }
                },
                "reason": {
                  "type": "string"
                }
              },
              "required": [
                "output_header",
                "source",
                "fallback",
                "transforms",
                "reason"
              ],
              "additionalProperties": false
            }
          },
          "detail_start_marker": {
            "type": [
              "string",
              "null"
            ]
          },
          "detail_end_marker": {
            "type": [
              "string",
              "null"
            ]
          },
          "line_item_granularity": {
            "type": [
              "string",
              "null"
            ],
            "enum": [
              "per_charge_row",
              "per_service_group",
              "per_total_group",
              null
            ]
          },
          "service_id_preference": {
            "type": [
              "string",
              "null"
            ],
            "enum": [
              "first_identifier",
              "parent_identifier",
              "total_row_identifier",
              "leftmost_identifier",
              "child_identifier",
              null
            ]
          },
          "billing_reference_preference": {
            "type": [
              "string",
              "null"
            ],
            "enum": [
              "same_as_service_id",
              "parent_identifier",
              "separate_column",
              "none",
              null
            ]
          },
          "service_id_column_label": {
            "type": [
              "string",
              "null"
            ]
          },
          "billing_reference_column_label": {
            "type": [
              "string",
              "null"
            ]
          },
          "amount_column_label": {
            "type": [
              "string",
              "null"
            ]
          },
          "tax_amount_column_label": {
            "type": [
              "string",
              "null"
            ]
          },
          "amount_source": {
            "type": [
              "string",
              "null"
            ],
            "enum": [
              "group_total",
              "first_amount",
              "label_amount",
              "label_amount_minus_tax",
              "table_charges_column",
              null
            ]
          },
          "tax_source": {
            "type": [
              "string",
              "null"
            ],
            "enum": [
              "none",
              "label_amount",
              "group_total_minus_amount",
              "table_tax_column",
              null
            ]
          },
          "tax_output_mode": {
            "type": [
              "string",
              "null"
            ],
            "enum": [
              "auto",
              "extract_exact",
              "calculate",
              "none",
              null
            ]
          },
          "tax_rate_source": {
            "type": [
              "string",
              "null"
            ],
            "enum": [
              "auto",
              "invoice_tax_rate",
              "invoice_tax_divided_by_subtotal",
              "consistent_line_tax_rate",
              null
            ]
          },
          "service_id_value_pattern": {
            "type": [
              "string",
              "null"
            ]
          },
          "billing_reference_value_pattern": {
            "type": [
              "string",
              "null"
            ]
          },
          "detail_table_anchors": {
            "type": "array",
            "items": {
              "type": "string"
            }
          },
          "table_column_labels": {
            "type": "array",
            "items": {
              "type": "string"
            }
          },
          "subtotal_keywords": {
            "type": "array",
            "items": {
              "type": "string"
            }
          },
          "tax_keywords": {
            "type": "array",
            "items": {
              "type": "string"
            }
          },
          "skip_row_keywords": {
            "type": "array",
            "items": {
              "type": "string"
            }
          },
          "include_zero_amount_line_items": {
            "type": "boolean"
          },
          "require_line_item_identifier": {
            "type": "boolean"
          }
        },
        "required": [
          "canonical_name",
          "aliases",
          "output_type",
          "notes",
          "field_overrides",
          "output_mapping_overrides",
          "detail_start_marker",
          "detail_end_marker",
          "line_item_granularity",
          "service_id_preference",
          "billing_reference_preference",
          "service_id_column_label",
          "billing_reference_column_label",
          "amount_column_label",
          "tax_amount_column_label",
          "amount_source",
          "tax_source",
          "tax_output_mode",
          "tax_rate_source",
          "service_id_value_pattern",
          "billing_reference_value_pattern",
          "detail_table_anchors",
          "table_column_labels",
          "subtotal_keywords",
          "tax_keywords",
          "skip_row_keywords",
          "include_zero_amount_line_items",
          "require_line_item_identifier"
        ],
        "additionalProperties": false
      }
    },
    "required": [
      "assistant_message",
      "open_questions",
      "confidence",
      "selected_plan_id",
      "profile"
    ],
    "additionalProperties": false
  }
}
```

## Response
```
{"assistant_message": "Mapped due date and set per-charge grouping.", "open_questions": ["Is VAT itemized per line?"], "confidence": 0.82, "profile": {"canonical_name": "Acme", "aliases": ["Acme Inc", "Acme Telecom"], "output_type": "standard", "notes": "Header is a label/value table on page 1.", "field_overrides": [{"field_path": "field.due_date", "label_hint": "Payment Due", "date_format": "%d/%m/%Y"}], "output_mapping_overrides": [], "detail_start_marker": "Service Charges", "detail_end_marker": null, "line_item_granularity": "per_charge_row", "service_id_preference": "first_identifier", "billing_reference_preference": "same_as_service_id", "service_id_column_label": "Service Number", "billing_reference_column_label": null, "amount_column_label": "Amount", "tax_amount_column_label": "Tax", "amount_source": "table_charges_column", "tax_source": "table_tax_column", "tax_output_mode": "extract_exact", "tax_rate_source": null, "service_id_value_pattern": null, "billing_reference_value_pattern": null, "detail_table_anchors": ["Service Charges"], "table_column_labels": ["Service", "Amount"], "subtotal_keywords": [], "tax_keywords": ["VAT"], "skip_row_keywords": ["Total Current Charges"], "include_zero_amount_line_items": false, "require_line_item_identifier": true}}
```
