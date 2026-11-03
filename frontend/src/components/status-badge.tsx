"use client";

import { Badge, BadgeDot } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { IntakeStatus, ExtractionPath, ModelStatus } from "@/types";

/**
 * Status pills.
 *
 * Words, not codes. Green means free or done, gold means money was spent or
 * something drifted, red means a person is needed, blue means in progress.
 * Every pill carries a word, never colour alone, so the table survives
 * greyscale.
 */

// ── Intake / invoice status ────────────────────────────────

export function StatusBadge({ status }: { status: IntakeStatus | string }) {
  switch (status) {
    case "completed":
      return (
        <Badge variant="success">
          <BadgeDot />
          Delivered
        </Badge>
      );
    case "completed_with_warnings":
      return (
        <Badge variant="warning">
          <BadgeDot />
          Variance
        </Badge>
      );
    case "failed":
      return (
        <Badge variant="destructive">
          <BadgeDot />
          Needs you
        </Badge>
      );
    case "processing":
      return (
        <Badge variant="cut">
          <BadgeDot />
          Running
        </Badge>
      );
    case "received":
      return (
        <Badge variant="neutral">
          <BadgeDot />
          Received
        </Badge>
      );
    default:
      return <Badge variant="neutral">{String(status).replace(/_/g, " ")}</Badge>;
  }
}

// ── Extraction path ────────────────────────────────────────

/**
 * Cost is always a pill, so the promise is visible on every row: Free in green
 * when the template ran, the paid path in gold.
 */
export function ExtractionPathBadge({ path }: { path: ExtractionPath | string }) {
  switch (path) {
    case "model":
      return (
        <Badge variant="success" title="Ran from the saved template at no AI cost">
          Free
        </Badge>
      );
    case "model_fallback_ai":
      return (
        <Badge variant="warning" title="The template did not hold; AI read this one">
          Fell back
        </Badge>
      );
    case "ai":
      return (
        <Badge variant="warning" title="Read with AI">
          Paid
        </Badge>
      );
    default:
      return <Badge variant="neutral">{String(path)}</Badge>;
  }
}

// ── Model lifecycle ────────────────────────────────────────

export function ModelStatusBadge({ status }: { status: ModelStatus | string }) {
  switch (status) {
    case "approved":
      return (
        <Badge variant="success">
          <BadgeDot />
          Approved
        </Badge>
      );
    case "candidate":
      return (
        <Badge variant="cut">
          <BadgeDot />
          Candidate
        </Badge>
      );
    case "failed_validation":
      return (
        <Badge variant="destructive">
          <BadgeDot />
          Failed
        </Badge>
      );
    case "retired":
      return <Badge variant="neutral">Retired</Badge>;
    default:
      return <Badge variant="neutral">{String(status).replace(/_/g, " ")}</Badge>;
  }
}

// ── Reconciliation — the signal that actually predicts a bad extraction ────

export function ReconciliationBadge({
  isReconciled,
  variance,
}: {
  isReconciled?: boolean | null;
  variance?: number | null;
}) {
  if (isReconciled === null || isReconciled === undefined) {
    return <span className="text-muted-foreground/70">—</span>;
  }
  if (isReconciled) {
    return (
      <span className="inline-flex items-center gap-1.5 text-[13px] font-medium text-success">
        <span aria-hidden="true">✓</span>
        Balanced
      </span>
    );
  }
  return (
    <span
      className="font-mono text-[13px] font-medium text-warning"
      title="Line items do not sum to the invoice total"
    >
      {variance != null
        ? `${variance > 0 ? "+" : ""}${variance.toLocaleString(undefined, {
            maximumFractionDigits: 2,
          })}`
        : "off"}
    </span>
  );
}

// ── Confidence (deprecated) ────────────────────────────────

/**
 * @deprecated The default extraction path hardcodes this to 1.0, so it measures
 * nothing. Kept only so un-migrated screens compile; use ReconciliationBadge.
 */
export function ConfidenceBadge({ confidence }: { confidence: number }) {
  return (
    <span className="font-mono text-xs text-muted-foreground">
      {(confidence * 100).toFixed(0)}%
    </span>
  );
}

// ── Charge type — structural, not semantic ─────────────────

const chargeTone: Record<string, "neutral" | "success" | "warning"> = {
  credit: "success",
  tax: "warning",
};

export function ChargeTypeBadge({ type }: { type: string }) {
  return (
    <Badge variant={chargeTone[type] ?? "neutral"} className={cn("normal-case")}>
      {type.replace(/_/g, " ")}
    </Badge>
  );
}
