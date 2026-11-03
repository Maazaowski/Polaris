"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Mascot, Confetti } from "@/components/brand/mascot";
import { RotateCcw, X } from "lucide-react";

/**
 * Shared data-surface states.
 *
 * A screen that renders a Loading gets an Error for free, so a failed request
 * never leaves a permanent skeleton that claims to be working.
 */

/** Something went wrong fetching. Always says what, and always offers a way out. */
export function ErrorState({
  what,
  onRetry,
  detail,
  className,
}: {
  /** The thing that failed to load, lowercase: "supplier profiles". */
  what: string;
  onRetry?: () => void;
  detail?: string;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-start gap-2 rounded-3xl bg-destructive-soft px-6 py-5 shadow-[inset_0_0_0_1px_#ffd9d9]",
        className,
      )}
    >
      <p className="eyebrow text-destructive">Could not load</p>
      <p className="text-[15px] font-medium text-foreground">
        {what.charAt(0).toUpperCase() + what.slice(1)} could not be loaded.
      </p>
      <p className="max-w-prose text-[14px] text-muted-foreground">
        {detail ?? "The API did not respond. It may be restarting. Retrying usually resolves it."}
      </p>
      {onRetry && (
        <Button variant="hairline" size="sm" onClick={onRetry} className="mt-1">
          <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
          Retry
        </Button>
      )}
    </div>
  );
}

/**
 * Nothing here yet. The mascot keeps it friendly; the action names what fills it.
 */
export function EmptyState({
  title,
  hint,
  action,
  className,
  tone = "blue",
  compact = false,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
  className?: string;
  tone?: "blue" | "green" | "yellow";
  /** Smaller mascot, less padding: for empty states inside a card. */
  compact?: boolean;
}) {
  return (
    <div
      className={cn(
        "relative flex flex-col items-center gap-3 overflow-hidden rounded-3xl bg-card px-6 text-center shadow-[inset_0_0_0_1px_var(--ring-card)]",
        compact ? "py-8" : "py-14",
        className,
      )}
    >
      {!compact && (
        <>
          <Confetti className="absolute top-4 left-6 h-36 w-36 opacity-90" />
          <Confetti className="absolute right-6 bottom-2 h-36 w-36 opacity-90" flip />
        </>
      )}
      <Mascot tone={tone} size={compact ? 72 : 120} />
      <p
        className={cn(
          "font-display font-semibold tracking-[-0.03em] text-foreground",
          compact ? "text-[20px]" : "text-[28px] leading-tight",
        )}
      >
        {title}
      </p>
      {hint && <p className="max-w-prose text-[15px] text-muted-foreground">{hint}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

/**
 * Loading placeholder matching the final geometry. Not pulsing: a pulse implies
 * progress the app cannot measure.
 */
export function LoadingState({
  rows = 5,
  className,
}: {
  rows?: number;
  className?: string;
}) {
  return (
    <div
      className={cn("overflow-hidden rounded-3xl bg-card shadow-[inset_0_0_0_1px_var(--ring-card)]", className)}
      aria-busy="true"
      aria-live="polite"
    >
      <span className="sr-only">Loading…</span>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="flex items-center gap-3 border-b border-border px-5 py-3.5 last:border-b-0"
        >
          <div className="h-2.5 w-24 rounded-full bg-secondary" />
          <div className="h-2.5 flex-1 rounded-full bg-secondary/70" />
          <div className="h-2.5 w-16 rounded-full bg-secondary/50" />
        </div>
      ))}
    </div>
  );
}

/**
 * An error that stays put, beside the control that failed, until resolved or
 * dismissed.
 */
export function InlineError({
  message,
  onDismiss,
  className,
}: {
  message?: string | null;
  onDismiss?: () => void;
  className?: string;
}) {
  if (!message) return null;
  return (
    <div
      role="alert"
      className={cn(
        "flex items-start gap-3 rounded-2xl bg-destructive-soft px-4 py-3 shadow-[inset_0_0_0_1px_#ffd9d9]",
        className,
      )}
    >
      <span className="min-w-0 flex-1">
        <span className="eyebrow block text-destructive">Not saved</span>
        {/* API messages can be multi-line (pydantic validation lists). */}
        <span className="mt-0.5 block whitespace-pre-line text-[14px] text-foreground">
          {message}
        </span>
      </span>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss error"
          className="shrink-0 text-muted-foreground transition-colors hover:text-foreground"
        >
          <X className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      )}
    </div>
  );
}
