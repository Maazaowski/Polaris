"""A delivered output column: one entry in a profile's or template's
``output_columns`` list.

This module is a leaf. It imports nothing else from ``polaris.output`` so the
writer, mapper, diff and the profile schema can all depend on it without
cycles.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

TRANSFORMS = ("digits_only", "trim", "uppercase", "lowercase")


class OutputColumn(BaseModel):
    """One column in the delivered output."""

    header: str = Field(..., description="Column header written to the deliverable")
    source: str = Field(
        default="",
        description=(
            "Where the value comes from: 'field.<name>' for a document field, "
            "'row.<name>' for a line-item field, or a derived value 'computed.<name>' "
            "(e.g. 'computed.line_tax')."
        ),
    )
    fallback: str | None = Field(
        default=None,
        description="Secondary path used when 'source' resolves to empty.",
    )
    transforms: list[str] = Field(
        default_factory=list,
        description="Safe value transforms applied after resolving source/fallback.",
    )
    width: int = Field(default=15, description="Column width hint for XLSX output")
    number_format: str | None = Field(
        default=None, description="openpyxl number format (e.g. '#,##0.00'); null = text"
    )

    model_config = {"extra": "ignore"}

    @field_validator("transforms")
    @classmethod
    def _allowed_unique_transforms(cls, value: list[str]) -> list[str]:
        unknown = [t for t in value if t not in TRANSFORMS]
        if unknown:
            raise ValueError(f"unknown output transforms: {', '.join(unknown)}")
        if len(value) != len(set(value)):
            raise ValueError("output transforms must not contain duplicates")
        if "uppercase" in value and "lowercase" in value:
            raise ValueError("output transforms cannot combine uppercase and lowercase")
        return value
