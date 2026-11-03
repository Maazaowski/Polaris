import { cn } from "@/lib/utils";

/**
 * The Polaris mark — the four-point star you steer by, with one small glint.
 *
 * Rules:
 *   - The star uses `currentColor`, so it inherits the theme.
 *   - The glint is the only colour in the lockup: the primary accent. At
 *     16px it is dropped (`glint={false}`), the star alone survives.
 *   - Two paths, no gradients, never rotated.
 */
export function Mark({
  className,
  glint = true,
}: {
  className?: string;
  /** Show the accent glint. Off below 32px and in one-colour contexts. */
  glint?: boolean;
  /** Kept for older call sites. */
  showCut?: boolean;
}) {
  return (
    <svg
      viewBox="0 0 28 24"
      className={cn("h-6 w-7 shrink-0", className)}
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M11 1.5c1.1 5.8 3.9 8.6 9.7 9.7-5.8 1.1-8.6 3.9-9.7 9.7-1.1-5.8-3.9-8.6-9.7-9.7 5.8-1.1 8.6-3.9 9.7-9.7z"
        fill="currentColor"
      />
      {glint && (
        <path
          d="M23 1c.5 2.5 1.7 3.7 4.2 4.2-2.5.5-3.7 1.7-4.2 4.2-.5-2.5-1.7-3.7-4.2-4.2 2.5-.5 3.7-1.7 4.2-4.2z"
          fill="var(--primary)"
        />
      )}
    </svg>
  );
}
