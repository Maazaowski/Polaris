"use client";

import { cn } from "@/lib/utils";
import type { PreviewReconciliation } from "@/types";

/**
 * The reconciliation panel.
 *
 * The operator's task on the invoice detail screen is exactly one thing: **find
 * the row that is wrong.** The page used to open with a processing log and make
 * them hunt for it.
 *
 * So this shows the arithmetic, explicitly, the way you would check it on paper:
 * what the line items add up to, what the invoice claims, and the difference.
 * When those agree it collapses to a single quiet line — a balanced invoice
 * needs no explanation.
 */
function Money({
  value,
  className,
  sign = false,
}: {
  value: number | null | undefined;
  className?: string;
  sign?: boolean;
}) {
  if (value === null || value === undefined) {
    return <span className="text-muted-foreground">—</span>;
  }
  const formatted = Math.abs(value).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  const prefix = sign ? (value > 0 ? "+" : value < 0 ? "−" : "") : value < 0 ? "−" : "";
  return (
    <span className={cn("font-mono [font-variant-numeric:tabular-nums]", className)}>
      {prefix}
      {formatted}
    </span>
  );
}

export function ReconciliationPanel({
  reconciliation,
  lineItemCount,
  className,
}: {
  reconciliation?: PreviewReconciliation | null;
  lineItemCount?: number;
  className?: string;
}) {
  if (!reconciliation) return null;

  const {
    is_reconciled,
    line_items_sum,
    computed_total,
    reconcile_target,
    stated_total,
    variance,
  } = reconciliation;
  const target = reconcile_target ?? stated_total;
  // The check compares the invoice's figure with the rows PLUS the tax and
  // fees it read off the invoice, not with the rows alone. Showing only the
  // row sum once put "8,184.21 vs 8,184.21, off by 1,258.47" on screen: the
  // rows already included tax and the stated tax was added on top. The added
  // term has to be on the card for the arithmetic to add up.
  const checkedTotal = computed_total ?? line_items_sum;
  const addedTaxAndFees =
    checkedTotal !== null &&
    checkedTotal !== undefined &&
    line_items_sum !== null &&
    line_items_sum !== undefined &&
    Math.abs(checkedTotal - line_items_sum) >= 0.005
      ? checkedTotal - line_items_sum
      : null;

  // Balanced: one line, no ceremony.
  if (is_reconciled) {
    return (
      <p
        className={cn("flex items-center gap-2 text-[14px] text-muted-foreground", className)}
      >
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-success" aria-hidden="true" />
        {lineItemCount ?? 0} line item{lineItemCount === 1 ? "" : "s"} balance to the invoice
        total.
      </p>
    );
  }

  return (
    <div className={cn("overflow-hidden rounded-3xl bg-warning-soft shadow-[inset_0_0_0_1px_#f3e3a0]", className)}>
      <div className="border-b border-[#f3e3a0] px-6 py-4">
        <p className="eyebrow text-warning">Does not balance</p>
        <p className="mt-0.5 text-[15px] text-foreground">
          The extracted rows do not add up to what the invoice says. One or more line items
          is wrong, missing, or double-counted.
          {addedTaxAndFees !== null && addedTaxAndFees > 0
            ? " If the rows already include tax, it is being counted twice."
            : ""}
        </p>
      </div>

      {/* The arithmetic, as you would check it on paper. */}
      <dl className="px-6 py-4 text-[14px]">
        <div className="flex items-baseline justify-between gap-6 py-0.5">
          <dt className="text-muted-foreground">
            {lineItemCount ?? 0} line item{lineItemCount === 1 ? "" : "s"} sum to
          </dt>
          <dd>
            <Money value={line_items_sum} />
          </dd>
        </div>
        {addedTaxAndFees !== null ? (
          <>
            <div className="flex items-baseline justify-between gap-6 py-0.5">
              <dt className="text-muted-foreground">Tax and fees read from the invoice</dt>
              <dd>
                <Money value={addedTaxAndFees} sign />
              </dd>
            </div>
            <div className="flex items-baseline justify-between gap-6 py-0.5">
              <dt className="text-muted-foreground">Checked total</dt>
              <dd>
                <Money value={checkedTotal} />
              </dd>
            </div>
          </>
        ) : null}
        <div className="flex items-baseline justify-between gap-6 py-0.5">
          <dt className="text-muted-foreground">Invoice states</dt>
          <dd>
            <Money value={target} />
          </dd>
        </div>
        <div className="mt-1 flex items-baseline justify-between gap-6 border-t border-[#f3e3a0] pt-1.5">
          <dt className="font-medium">Off by</dt>
          <dd>
            <Money value={variance} sign className="font-semibold text-warning" />
          </dd>
        </div>
      </dl>
    </div>
  );
}
