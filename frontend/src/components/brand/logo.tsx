import Link from "next/link";
import { cn } from "@/lib/utils";
import { Mark } from "./mark";

/**
 * The Polaris logo: the star mark and the word, Inter 600 with tight tracking.
 * Ink inherits `currentColor` so it works on either theme.
 */
type LogoVariant = "primary" | "mark" | "wordmark" | "mono";

const WORDMARK_CLASS =
  "font-sans font-semibold leading-none tracking-[-0.2px] text-[16px] select-none";

export function Logo({
  variant = "primary",
  className,
  href = "/",
}: {
  variant?: LogoVariant;
  className?: string;
  /** Omit to render a non-navigating lockup (login, print, exports). */
  href?: string | null;
}) {
  const content =
    variant === "mark" ? (
      <Mark className="h-5 w-5" />
    ) : variant === "wordmark" ? (
      <span className={WORDMARK_CLASS}>Polaris</span>
    ) : (
      <span className="flex items-center gap-2">
        <Mark className="h-[18px] w-[18px]" />
        <span className={WORDMARK_CLASS}>Polaris</span>
      </span>
    );

  const classes = cn(
    "inline-flex items-center text-foreground",
    href && "rounded-sm outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
    className,
  );

  if (!href) {
    return (
      <span className={classes} role="img" aria-label="Polaris">
        {content}
      </span>
    );
  }

  return (
    <Link href={href} className={classes} aria-label="Polaris home">
      {content}
    </Link>
  );
}
