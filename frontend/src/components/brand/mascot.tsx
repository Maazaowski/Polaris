import { cn } from "@/lib/utils";

/**
 * The Polaris mascot — a star with a face — and the confetti that follows it.
 *
 * They live in empty states, the upload zone, sign in and "all clear" cards.
 * Never in a table, never beside data. The star bobs slowly unless the user
 * prefers reduced motion.
 */
const TONES = {
  blue: { back: "#7dc4ff", front: "#4dafff", glow: "rgba(55,132,244,.25)" },
  green: { back: "#6fd8a0", front: "#44c67f", glow: "rgba(68,198,127,.28)" },
  yellow: { back: "#ffdca0", front: "#ffcf7b", glow: "rgba(202,146,48,.25)" },
} as const;

export function Mascot({
  tone = "blue",
  size = 140,
  className,
  bob = true,
}: {
  tone?: keyof typeof TONES;
  size?: number;
  className?: string;
  bob?: boolean;
}) {
  const t = TONES[tone];
  return (
    <svg
      viewBox="0 0 140 140"
      width={size}
      height={size}
      aria-hidden="true"
      focusable="false"
      className={cn(bob && "bob", className)}
      style={{ filter: `drop-shadow(0 12px 18px ${t.glow})` }}
    >
      <path
        d="M70 6c6 24 18 36 42 42-24 6-36 18-42 42-6-24-18-36-42-42 24-6 36-18 42-42z"
        fill={t.back}
        transform="translate(0,8) scale(1.1) translate(-7,-7)"
      />
      <path
        d="M70 6c6 24 18 36 42 42-24 6-36 18-42 42-6-24-18-36-42-42 24-6 36-18 42-42z"
        fill={t.front}
        transform="translate(0,4) scale(1.1) translate(-7,-7)"
      />
      <circle cx="60" cy="56" r="4.5" fill="#171717" />
      <circle cx="80" cy="56" r="4.5" fill="#171717" />
      <circle cx="61.5" cy="54.5" r="1.4" fill="#fff" />
      <circle cx="81.5" cy="54.5" r="1.4" fill="#fff" />
      <path d="M61 68q9 8 18 0" stroke="#171717" strokeWidth="3" fill="none" strokeLinecap="round" />
      <circle cx="52" cy="64" r="4" fill="#f966ac" opacity=".55" />
      <circle cx="88" cy="64" r="4" fill="#f966ac" opacity=".55" />
    </svg>
  );
}

/** Pastel shapes scattered behind a mascot. Absolutely positioned by the caller. */
export function Confetti({ className, flip = false }: { className?: string; flip?: boolean }) {
  return (
    <svg
      viewBox="0 0 200 200"
      aria-hidden="true"
      focusable="false"
      className={cn("pointer-events-none", className)}
      style={flip ? { transform: "scaleX(-1)" } : undefined}
    >
      <circle cx="40" cy="40" r="22" fill="#7dc4ff" />
      <circle cx="150" cy="30" r="9" fill="#ffcf7b" />
      <path d="M20 150l16-28 16 28z" fill="#44c67f" />
      <circle cx="120" cy="140" r="6" fill="#f966ac" />
      <rect x="160" y="110" width="18" height="18" rx="5" fill="#ffcf7b" transform="rotate(20 169 119)" />
      <path d="M80 100c10-14 30-14 40 0" stroke="#ff5310" strokeWidth="5" fill="none" strokeLinecap="round" />
      <circle cx="170" cy="170" r="5" fill="#9553f9" />
    </svg>
  );
}
