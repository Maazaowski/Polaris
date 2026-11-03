import { cn } from "@/lib/utils";

/**
 * The Polaris mark — a four-point star in a single ink.
 *
 * Rules:
 *   - Ink uses `currentColor`, so the mark inherits the theme. Never a fill.
 *   - One path, so it survives 16px.
 */
export function Mark({
  className,
}: {
  className?: string;
  /** Kept for older call sites; the star has no accent to toggle. */
  showCut?: boolean;
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={cn("h-6 w-6 shrink-0", className)}
      fill="currentColor"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M12 1.5c1.2 6.3 4.2 9.3 10.5 10.5C16.2 13.2 13.2 16.2 12 22.5 10.8 16.2 7.8 13.2 1.5 12 7.8 10.8 10.8 7.8 12 1.5z" />
    </svg>
  );
}
