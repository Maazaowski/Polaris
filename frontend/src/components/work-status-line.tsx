"use client";

import Link from "next/link";
import { useDashboardStats } from "@/hooks/use-dashboard";
import { cn } from "@/lib/utils";

/**
 * The four numbers that open the queue: ran free, paid AI, balanced, needs you.
 * Each is a beige card; the one that needs a person is tinted red and links to
 * the review list.
 */
function Figure({
  label,
  value,
  note,
  href,
  tone = "default",
  title,
  className,
}: {
  label: string;
  value: React.ReactNode;
  note?: React.ReactNode;
  href?: string;
  tone?: "default" | "alert";
  title?: string;
  className?: string;
}) {
  const body = (
    <>
      <span className="text-[14px] font-medium text-muted-foreground">{label}</span>
      <span
        className={cn(
          "font-display text-[40px] leading-none font-medium tracking-[-0.03em] text-foreground [font-variant-numeric:tabular-nums]",
          tone === "alert" && "text-destructive",
        )}
      >
        {value}
      </span>
      {note && <span className="text-[14px]">{note}</span>}
    </>
  );

  const classes = cn(
    "flex flex-col gap-2.5 rounded-3xl bg-card px-6 py-5 shadow-[inset_0_0_0_1px_var(--ring-card)] transition-transform duration-200 ease-out-expo",
    tone === "alert" && "bg-destructive-soft shadow-[inset_0_0_0_1px_#ffd9d9]",
    href && "hover:-translate-y-0.5",
    className,
  );

  if (!href) {
    return (
      <div className={classes} title={title}>
        {body}
      </div>
    );
  }
  return (
    <Link href={href} className={classes} title={title}>
      {body}
    </Link>
  );
}

export function WorkStatusLine({ className }: { className?: string }) {
  const { data: stats, isLoading, isError } = useDashboardStats();

  // A broken stats call must not take the queue down with it.
  if (isError) return null;

  if (isLoading || !stats) {
    return (
      <div className={cn("grid gap-4 sm:grid-cols-2 xl:grid-cols-4", className)} aria-busy="true">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="h-[118px] rounded-3xl bg-card shadow-[inset_0_0_0_1px_var(--ring-card)]"
          />
        ))}
      </div>
    );
  }

  const free = stats.model_path_count ?? 0;
  const scored = stats.scored_jobs ?? 0;
  const reconciled = stats.reconciled_jobs ?? 0;
  const needs = stats.pending_exceptions ?? 0;
  const paid = stats.ai_path_count ?? 0;

  return (
    <div className={cn("fade-up fade-up-1 grid gap-4 sm:grid-cols-2 xl:grid-cols-4", className)}>
      <Figure
        label="Ran free"
        value={free}
        note={
          free > 0 ? (
            <span className="inline-flex items-center gap-2 font-medium text-section-suppliers">
              <span aria-hidden="true">✓</span>Read by a template at $0
            </span>
          ) : (
            <span className="text-muted-foreground">No template has run yet</span>
          )
        }
        href="/invoices?path=model"
        title="Extracted from a saved template at no AI cost"
      />
      <Figure
        label="Paid AI"
        value={paid}
        note={
          paid > 0 ? (
            <span className="font-medium text-section-templates">
              {stats.total_ai_cost != null ? `$${stats.total_ai_cost.toFixed(2)} this period` : "Read with AI"}
            </span>
          ) : (
            <span className="text-muted-foreground">Nothing paid for yet</span>
          )
        }
        href="/invoices?path=ai"
        title="Read with AI because no template matched"
      />
      <Figure
        label="Balanced"
        value={
          <>
            {reconciled}
            <span className="text-[20px] text-muted-foreground">/{scored}</span>
          </>
        }
        note={
          <span className="inline-flex items-center gap-2 font-medium text-section-suppliers">
            <span aria-hidden="true">✓</span>
            {`${(stats.success_rate ?? 0).toFixed(0)}% match the printed total`}
          </span>
        }
        title={`${reconciled} of ${scored} extractions balance to the invoice total`}
      />
      <Figure
        label="Needs you"
        value={needs}
        tone={needs > 0 ? "alert" : "default"}
        note={
          needs > 0 ? (
            <span className="font-medium text-destructive">Open the review list →</span>
          ) : (
            <span className="text-muted-foreground">Nothing is waiting on a person</span>
          )
        }
        href="/exceptions"
        title="Failed, plus delivered with a variance"
      />
    </div>
  );
}
