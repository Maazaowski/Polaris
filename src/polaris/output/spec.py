"""Configurable output specification — the customer-defined deliverable contract.

An ``OutputSpec`` is configuration (like a supplier profile): it declares which
columns the customer's downstream system expects, in order, and how each column
maps to canonical invoice data. The standard 8-column format is just the first
shipped spec, not a hardcoded constant.

This module is a leaf — it imports nothing else from ``polaris.output`` so
the writer, mapper, diff, and loader can all depend on it without cycles.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from polaris.output.columns import OutputColumn


class OutputSpec(BaseModel):
    """A named, versioned set of output columns a customer requires."""

    __column_type__ = OutputColumn

    spec_id: str = Field(..., description="e.g. 'standard.8col'")
    name: str = Field(default="", description="Human-readable label")
    columns: list[OutputColumn] = Field(..., min_length=1)

    model_config = {"extra": "ignore"}
