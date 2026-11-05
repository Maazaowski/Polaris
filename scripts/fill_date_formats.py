"""Fill the printed date formats a profile's delivered date fields are missing.

Why this exists: every date a profile delivers must carry the strptime format
the supplier prints (``FieldDef.date_format``), or day/month ambiguity corrupts
the deliverable silently. Profiles migrated from the old shared registries have
none, so they save with a warning but cannot be retrained or activated, and
nothing in the product infers a document-field format. This script reads the
printed dates off each profile's archived invoices (the model's authoring
invoice first, then the newest completed intakes), tries every known format
against every sample, and writes a format only when exactly one fits. A
printed form several formats fit (``02/12/2025``: 2 December or 12 February)
is reported with both readings and the exact ``--set`` line that resolves it,
for a human to decide. ``date_format`` is not a fingerprint input, so the save
re-keys no model.

Usage (from the repo root, with POLARIS_* pointing at the target DB and work dir):

    python scripts/fill_date_formats.py                         # dry run, every profile with gaps
    python scripts/fill_date_formats.py --profile colt.standard.v1 --samples 5
    python scripts/fill_date_formats.py --apply                 # write the unambiguous formats
    python scripts/fill_date_formats.py --set eunetworks.standard.v2:field.invoice_date=%d/%m/%Y --apply
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402

from polaris import audit  # noqa: E402
from polaris.db import crud  # noqa: E402
from polaris.db import session as db_session  # noqa: E402
from polaris.db.models import IntakeRecord  # noqa: E402
from polaris.extraction import normalization  # noqa: E402
from polaris.extraction.layout import LayoutDocument, extract_layout_document  # noqa: E402
from polaris.fields import coercion  # noqa: E402
from polaris.fields.catalogue import field_path  # noqa: E402
from polaris.fields.schema import FieldDef, FieldScope, FieldType  # noqa: E402
from polaris.models import registry  # noqa: E402
from polaris.profiles import loader  # noqa: E402
from polaris.profiles.contract import _canonical_to_contract_path, field_set, output_columns  # noqa: E402
from polaris.profiles.schema import SupplierProfile  # noqa: E402

SCRIPT_NAME = "fill_date_formats.py"

# Every strptime format the pipeline itself knows how to read, coercion's list
# first, then the normalizer's, without repeats: a format this script writes is
# one the pipeline would have accepted anyway.
CANDIDATE_FORMATS: tuple[str, ...] = tuple(
    dict.fromkeys(coercion._FALLBACK_DATE_FORMATS + normalization._DATE_FORMATS)
)

# The normalizer's _DATE_VALUE_RE has no ``dd-Mon-yyyy`` shape, so it finds no
# date on a Colt invoice ("Invoice Date 01-Feb-2024"). This is its union with
# the shapes coercion.parse_date_value falls back to, bounded so a date inside
# a longer token is not cut out of it. Month-year alone ("February 2024") is
# left out on purpose: it is not a full date and no candidate format fits it.
_PRINTED_DATE_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    r"\d{4}[-/]\d{1,2}[-/]\d{1,2}"  # 2024-02-01, 2024/02/01
    r"|\d{4}\s+\d{1,2}\s+\d{1,2}"  # 2024 02 01
    r"|\d{1,2}[-/ .][A-Za-z]{3,9}\.?[-/ .]\d{2,4}"  # 01-Feb-2024, 01 Feb 2024, 01 Feb. 2024
    r"|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}"  # 01/02/2024, 01.02.2024, 01-02-2024
    r"|[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{2,4}"  # Feb. 1, 2024, February 1 2024
    r")(?![0-9])",
    re.IGNORECASE,
)
_DATE_WORD_RE = re.compile(r"\bdate\b|\bdue\b|\bperiod\b", re.IGNORECASE)
_ROW_PERIOD_FIELDS = {"billing_period_start": 0, "billing_period_end": 1}
_MAX_PERIODS_PER_PDF = 20
_ROWS_BELOW_LABEL = 4

STATUS_SET = "set"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_UNPARSED = "unparsed"
STATUS_NOT_FOUND = "not found"
STATUS_OVERRIDE = "override"
STATUS_SKIPPED = "skipped"


@dataclass
class FieldInference:
    """What the archived invoices say about one delivered date field."""

    path: str
    field: FieldDef
    status: str
    format: str | None = None
    samples: list[str] = field(default_factory=list)
    candidates: list[str] = field(default_factory=list)
    label: str | None = None
    context_rows: list[str] = field(default_factory=list)
    note: str | None = None

    @property
    def writable(self) -> bool:
        return self.status in (STATUS_SET, STATUS_OVERRIDE) and bool(self.format)


@dataclass
class ProfileReport:
    profile_id: str
    profile_status: str
    samples: list[tuple[str, Path]] = field(default_factory=list)
    inferences: list[FieldInference] = field(default_factory=list)
    skipped_reason: str | None = None
    applied: bool = False

    def count(self, status: str) -> int:
        return sum(1 for inference in self.inferences if inference.status == status)

    @property
    def writable(self) -> list[FieldInference]:
        return [inference for inference in self.inferences if inference.writable]


# ---------------------------------------------------------------------------
# Gaps
# ---------------------------------------------------------------------------


def missing_date_paths(profile: SupplierProfile) -> list[tuple[str, FieldDef]]:
    """Every delivered date without a printed format, as ``(contract path, resolved field)``.

    Walks the output columns' source and fallback paths the way
    ``contract.date_format_issues`` does, so the two always agree on what is
    missing; the field comes back resolved (catalogue type and label merged in).
    """
    known = {field_path(f): f for f in field_set(profile).fields}
    gaps: dict[str, FieldDef] = {}
    for column in output_columns(profile):
        for path in (column.source, column.fallback):
            if not path:
                continue
            contract_path = _canonical_to_contract_path(path)
            resolved = known.get(contract_path)
            if resolved is not None and resolved.type == FieldType.DATE and not resolved.date_format:
                gaps.setdefault(contract_path, resolved)
    return list(gaps.items())


# ---------------------------------------------------------------------------
# Archived invoices
# ---------------------------------------------------------------------------


def archived_pdfs_for_profile(db: Any, profile_id: str, limit: int = 3) -> list[tuple[str, Path]]:
    """Up to ``limit`` archived PDFs for the profile as ``(intake id, path)``:
    the approved model's authoring invoice, then the candidate's, then the
    profile's completed intakes newest first. Only PDFs present on this host."""
    found: list[tuple[str, Path]] = []
    seen_paths: set[Path] = set()

    def consider(intake: IntakeRecord | None) -> None:
        if intake is None or len(found) >= limit:
            return
        pdf = registry._archived_pdf_for(intake)
        if pdf is None:
            return
        resolved = pdf.resolve()
        if resolved in seen_paths:
            return
        seen_paths.add(resolved)
        found.append((intake.id, pdf))

    for status in ("approved", "candidate"):
        model = crud.find_model_by_profile(db, profile_id, status=status)
        if model is not None and model.created_from_intake:
            consider(crud.get_intake(db, model.created_from_intake))

    if len(found) < limit:
        stmt = (
            select(IntakeRecord)
            .where(IntakeRecord.supplier_profile_id == profile_id, IntakeRecord.status == "completed")
            .order_by(IntakeRecord.created_at.desc(), IntakeRecord.id.desc())
        )
        for intake in db.scalars(stmt):
            if len(found) >= limit:
                break
            consider(intake)
    return found


# ---------------------------------------------------------------------------
# Reading printed dates
# ---------------------------------------------------------------------------


def _label_pattern(label: str) -> re.Pattern[str]:
    return re.compile(re.escape(label.strip()).replace(r"\ ", r"\s+"), re.IGNORECASE)


def printed_document_date(document: LayoutDocument, label: str) -> str | None:
    """The date printed against ``label``: the first date text after the label
    on its own row, else the first date text in a cell under the label cell
    (horizontally overlapping it) within the next four rows. Exactly as
    printed, so the caller can match a format against it."""
    if not label.strip():
        return None
    pattern = _label_pattern(label)
    for page in document.pages:
        rows = list(page.visual_rows)
        for index, row in enumerate(rows):
            match = pattern.search(row.text)
            if match is None:
                continue
            inline = _PRINTED_DATE_RE.search(row.text, match.end())
            if inline:
                return inline.group(0)
            label_cell = normalization._matching_label_cell(row, pattern)
            if label_cell is None:
                continue
            for next_row in rows[index + 1:index + 1 + _ROWS_BELOW_LABEL]:
                for cell in next_row.cells:
                    if normalization._cells_overlap_horizontally(label_cell, cell):
                        below = _PRINTED_DATE_RE.search(cell.text)
                        if below:
                            return below.group(0)
    return None


def _is_period_cell(cell: Any) -> bool:
    if cell.role == "billing_period":
        return True
    # The layout only tags periods printed with month names; a slash-dated
    # "01/12/2025 - 31/12/2025" is a plain text cell, so recognise it here by
    # its two date-shaped halves.
    parts = normalization._billing_period_parts(cell.text)
    return len(parts) == 2 and all(_PRINTED_DATE_RE.fullmatch(part.strip()) for part in parts)


def printed_row_periods(document: LayoutDocument, part_index: int, limit: int = _MAX_PERIODS_PER_PDF) -> list[str]:
    """The start (``part_index`` 0) or end (1) half of every billing-period
    cell, deduplicated, at most ``limit`` per document."""
    out: list[str] = []
    seen: set[str] = set()
    for page in document.pages:
        for row in page.visual_rows:
            for cell in row.cells:
                if not _is_period_cell(cell):
                    continue
                parts = normalization._billing_period_parts(cell.text)
                if len(parts) <= part_index:
                    continue
                text = parts[part_index].strip()
                if text and text not in seen:
                    seen.add(text)
                    out.append(text)
                    if len(out) >= limit:
                        return out
    return out


def _dated_context_rows(documents: list[LayoutDocument], limit: int = 2) -> list[str]:
    """Rows that print a date next to a date/due/period word, to show what the
    invoice calls the field when the configured label is not found."""
    out: list[str] = []
    for document in documents:
        for page in document.pages:
            for row in page.visual_rows:
                if _DATE_WORD_RE.search(row.text) and _PRINTED_DATE_RE.search(row.text):
                    out.append(f"{row.row_id or f'p{row.page}.r{row.row_index}'}: {row.text.strip()[:120]}")
                    if len(out) >= limit:
                        return out
    return out


# ---------------------------------------------------------------------------
# Formats
# ---------------------------------------------------------------------------


def _parses(text: str, fmt: str) -> bool:
    try:
        datetime.strptime(text, fmt)
    except (ValueError, TypeError):
        return False
    return True


def _formats_for(sample: str) -> set[str]:
    # The format must reproduce the printed text; the variants coercion also
    # tries (dropping a dotted month's dot) are a fallback for when none does,
    # so "Feb. 1, 2024" yields "%b. %d, %Y" and not "%b %d, %Y" as well.
    exact = {fmt for fmt in CANDIDATE_FORMATS if _parses(sample, fmt)}
    if exact:
        return exact
    variants = coercion._date_text_variants(sample)[1:]
    return {fmt for fmt in CANDIDATE_FORMATS for variant in variants if _parses(variant, fmt)}


def formats_parsing_all(samples: list[str]) -> list[str]:
    """The candidate formats that parse every sample, in candidate order.
    strptime enforces month <= 12 and the ``%Y`` width, so a day above 12 or
    a month name disambiguates on its own; otherwise several samples do."""
    if not samples:
        return []
    per_sample = [_formats_for(sample) for sample in samples]
    return [fmt for fmt in CANDIDATE_FORMATS if all(fmt in fits for fits in per_sample)]


def _reading(sample: str, fmt: str) -> str:
    for variant in coercion._date_text_variants(sample):
        try:
            return datetime.strptime(variant, fmt).date().isoformat()
        except (ValueError, TypeError):
            continue
    return "?"


def _validate_format(fmt: str) -> None:
    """A format must survive a strftime/strptime round trip, or it is a typo."""
    probe = date(2024, 2, 1)
    try:
        printed = probe.strftime(fmt)
        parsed = datetime.strptime(printed, fmt).date()
    except (ValueError, TypeError) as exc:
        raise ValueError(f"'{fmt}' is not a usable strptime format: {exc}") from exc
    if not printed.strip() or parsed != probe:
        raise ValueError(f"'{fmt}' does not round-trip a date: {probe} prints as '{printed}', reads as {parsed}")


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------


def _load_layouts(samples: list[tuple[str, Path]]) -> tuple[list[tuple[str, Path]], list[LayoutDocument], list[str]]:
    usable: list[tuple[str, Path]] = []
    documents: list[LayoutDocument] = []
    problems: list[str] = []
    for intake_id, pdf in samples:
        try:
            documents.append(extract_layout_document(pdf, include_markdown=False))
        except Exception as exc:  # a corrupt or unreadable archive is reported, not fatal
            problems.append(f"{intake_id}: cannot read {pdf} ({exc})")
            continue
        usable.append((intake_id, pdf))
    return usable, documents, problems


def _collect_samples(path: str, gap: FieldDef, documents: list[LayoutDocument]) -> tuple[list[str], str | None]:
    """The printed texts for one gap across the documents, plus a note when the
    field is not one this script knows how to read."""
    samples: list[str] = []
    if gap.scope == FieldScope.ROW:
        part_index = _ROW_PERIOD_FIELDS.get(gap.name)
        if part_index is None:
            return [], f"row field '{gap.name}' is not a billing period; set it with --set"
        for document in documents:
            for text in printed_row_periods(document, part_index):
                if text not in samples:
                    samples.append(text)
        return samples, None
    label = (gap.label_hint or "").strip()
    if not label:
        return [], "no label hint to look for; give the field a label hint or set the format with --set"
    for document in documents:
        text = printed_document_date(document, label)
        if text and text not in samples:
            samples.append(text)
    return samples, None


def infer_profile(
    db: Any,
    profile: SupplierProfile,
    *,
    samples: int = 3,
    overrides: dict[str, str] | None = None,
) -> ProfileReport:
    """Decide, per missing format, what the archived invoices support."""
    overrides = overrides or {}
    report = ProfileReport(profile_id=profile.profile_id, profile_status=profile.status)
    gaps = missing_date_paths(profile)
    if not gaps:
        return report

    archived = archived_pdfs_for_profile(db, profile.profile_id, limit=samples)
    usable, documents, problems = _load_layouts(archived)
    report.samples = usable
    needs_reading = [path for path, _ in gaps if path not in overrides]
    if not documents and needs_reading:
        report.skipped_reason = "; ".join(problems) if problems else "no archived invoice to read"

    for path, gap in gaps:
        label = (gap.label_hint or "").strip() or None
        if path in overrides:
            report.inferences.append(FieldInference(
                path=path, field=gap, status=STATUS_OVERRIDE, format=overrides[path], label=label,
            ))
            continue
        if not documents:
            report.inferences.append(FieldInference(path=path, field=gap, status=STATUS_SKIPPED, label=label))
            continue
        printed, note = _collect_samples(path, gap, documents)
        candidates = formats_parsing_all(printed)
        if not printed:
            status = STATUS_NOT_FOUND
        elif len(candidates) == 1:
            status = STATUS_SET
        elif candidates:
            status = STATUS_AMBIGUOUS
        else:
            status = STATUS_UNPARSED
        report.inferences.append(FieldInference(
            path=path,
            field=gap,
            status=status,
            format=candidates[0] if status == STATUS_SET else None,
            samples=printed,
            candidates=candidates,
            label=label,
            context_rows=_dated_context_rows(documents) if status == STATUS_NOT_FOUND else [],
            note=note,
        ))
    return report


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def apply_report(db: Any, profile: SupplierProfile, report: ProfileReport, *, by: str) -> list[str]:
    """Write the set/override formats into the profile's fields, save the
    profile, and record one audit event naming what was filled. Returns the
    paths written."""
    writable = report.writable
    if not writable:
        return []
    formats: dict[str, str] = {}
    for inference in writable:
        gap = inference.field
        entry = next((f for f in profile.fields if f.scope == gap.scope and f.name == gap.name), None)
        if entry is None:
            # An always-on catalogue field the profile never listed: list it now
            # with the format only, the catalogue still supplies type and role.
            entry = FieldDef(name=gap.name, scope=gap.scope, date_format=inference.format)
            profile.fields.append(entry)
        else:
            entry.date_format = inference.format
        formats[inference.path] = inference.format or ""
    loader.save_profile(profile, actor=None)
    audit.append_event(
        db,
        entity_type="profile",
        entity_id=profile.profile_id,
        action="date_formats_filled",
        actor=None,
        metadata={
            "by": by,
            "formats": formats,
            "source_intakes": [intake_id for intake_id, _ in report.samples],
            "overrides": [inference.path for inference in writable if inference.status == STATUS_OVERRIDE],
        },
    )
    db.commit()
    report.applied = True
    return list(formats)


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def parse_set_args(values: list[str]) -> dict[str, dict[str, str]]:
    """``profile_id:path=FORMAT`` lines as ``{profile_id: {path: format}}``.
    Raises ValueError on a malformed line or a format that does not round-trip."""
    overrides: dict[str, dict[str, str]] = {}
    for raw in values:
        head, sep, fmt = raw.partition("=")
        profile_id, colon, path = head.partition(":")
        if not sep or not colon or not profile_id.strip() or not path.strip() or not fmt.strip():
            raise ValueError(f"--set expects profile_id:path=FORMAT, got '{raw}'")
        path = _canonical_to_contract_path(path.strip())
        _validate_format(fmt)
        overrides.setdefault(profile_id.strip(), {})[path] = fmt
    return overrides


def _status_label(inference: FieldInference, applied: bool) -> str:
    if inference.status in (STATUS_SET, STATUS_OVERRIDE) and not applied:
        return f"would {inference.status}"
    return inference.status


def print_report(report: ProfileReport, *, apply: bool) -> None:
    print(f"{report.profile_id} ({report.profile_status})")
    if report.skipped_reason:
        print(f"  skipped: {report.skipped_reason}")
    if report.samples:
        print("  samples: " + ", ".join(intake_id for intake_id, _ in report.samples))
    for inference in report.inferences:
        shown = ", ".join(inference.samples[:5]) + (" ..." if len(inference.samples) > 5 else "")
        print(
            f"  {inference.path:30} {inference.format or '-':14} {_status_label(inference, apply):16}"
            + (f" samples: {shown}" if shown else "")
        )
        if inference.note:
            print(f"      {inference.note}")
        if inference.status == STATUS_AMBIGUOUS:
            for fmt in inference.candidates:
                readings = ", ".join(_reading(sample, fmt) for sample in inference.samples[:5])
                print(f"      {fmt:14} reads {readings}")
            print("      resolve with one of:")
            for fmt in inference.candidates:
                print(f"        --set {report.profile_id}:{inference.path}={fmt}")
        elif inference.status == STATUS_NOT_FOUND and inference.label:
            print(f"      label '{inference.label}' not found")
            for row in inference.context_rows:
                print(f"      row with a date: {row}")
    print()


def _summary_line(reports: list[ProfileReport]) -> str:
    counts = {status: sum(report.count(status) for report in reports)
              for status in (STATUS_SET, STATUS_OVERRIDE, STATUS_AMBIGUOUS, STATUS_UNPARSED, STATUS_NOT_FOUND)}
    skipped = sum(1 for report in reports if report.skipped_reason)
    return (
        f"{counts[STATUS_SET]} set, {counts[STATUS_OVERRIDE]} override, {counts[STATUS_AMBIGUOUS]} ambiguous, "
        f"{counts[STATUS_UNPARSED]} unparsed, {counts[STATUS_NOT_FOUND]} not found, "
        f"{skipped} profile(s) skipped."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", action="append", default=[], help="profile id to fill (repeatable; default: all)")
    parser.add_argument("--samples", type=int, default=3, help="archived invoices to read per profile (default 3)")
    parser.add_argument(
        "--set", action="append", default=[], metavar="PROFILE:PATH=FORMAT",
        help="force a format for one gap, e.g. eunetworks.standard.v2:field.invoice_date=%%d/%%m/%%Y (repeatable)",
    )
    parser.add_argument("--apply", action="store_true", help="write the set/override formats (default: dry run)")
    parser.add_argument("--by", default=SCRIPT_NAME, help="recorded in the audit event")
    args = parser.parse_args(argv)
    if args.samples < 1:
        print("--samples must be at least 1", file=sys.stderr)
        return 2
    try:
        overrides = parse_set_args(args.set)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        profiles = loader.load_all_profiles()
    except SQLAlchemyError as exc:
        print(f"cannot read profiles: {exc}", file=sys.stderr)
        return 1
    selected = [profiles[pid] for pid in args.profile if pid in profiles] if args.profile else list(profiles.values())
    unknown = [pid for pid in args.profile if pid not in profiles]
    unknown.extend(pid for pid in overrides if pid not in profiles)
    if unknown:
        print(f"unknown profile(s): {', '.join(dict.fromkeys(unknown))}", file=sys.stderr)
        return 2
    for profile_id, paths in overrides.items():
        gaps = {path for path, _ in missing_date_paths(profiles[profile_id])}
        stray = [path for path in paths if path not in gaps]
        if stray:
            print(
                f"{profile_id}: {', '.join(stray)} is not a delivered date field missing its format "
                f"(gaps: {', '.join(sorted(gaps)) or 'none'})",
                file=sys.stderr,
            )
            return 2
        if profile_id not in {p.profile_id for p in selected}:
            selected.append(profiles[profile_id])

    db = db_session.SessionLocal()
    try:
        mode = "APPLY" if args.apply else "DRY RUN"
        reports: list[ProfileReport] = []
        complete = 0
        for profile in selected:
            if not missing_date_paths(profile):
                complete += 1
                continue
            report = infer_profile(db, profile, samples=args.samples, overrides=overrides.get(profile.profile_id))
            if args.apply:
                apply_report(db, profile, report, by=args.by)
            reports.append(report)
        print(f"{mode}: {len(reports)} profile(s) with missing date formats, {complete} already complete\n")
        for report in reports:
            print_report(report, apply=args.apply)
        print(_summary_line(reports))
        pending = sum(len(report.writable) for report in reports)
        if not args.apply and pending:
            print(f"{pending} format(s) would be written. Re-run with --apply to write.")
        return 0
    except (SQLAlchemyError, OSError) as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
