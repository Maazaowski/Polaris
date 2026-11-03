import { mergeProps } from "@base-ui/react/merge-props"
import { useRender } from "@base-ui/react/use-render"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

/**
 * Pill — the status vocabulary.
 *
 * Soft tint, dark text of the same hue, 24px tall, Inter 500 at 13px. Every
 * pair passes 4.5:1. Green means free or done, gold means money was spent or
 * something drifted, red means a person is needed, blue means in progress.
 *
 * `success`/`warning`/`destructive`/`cut`/`neutral` are the real variants; the
 * rest are aliases kept so existing call sites compile.
 */
const badgeVariants = cva(
  "group/badge inline-flex h-6 w-fit shrink-0 items-center justify-center gap-1.5 overflow-hidden rounded-full px-2.5 text-[13px] leading-none font-medium tracking-[-0.09px] whitespace-nowrap transition-colors [&>svg]:pointer-events-none [&>svg]:size-3!",
  {
    variants: {
      variant: {
        /** Delivered, free, balanced, approved. */
        success: "bg-success-soft text-success",
        /** Paid AI, drift, variance: look, but nothing is broken. */
        warning: "bg-warning-soft text-warning",
        /** Failed, or a person is needed. */
        destructive: "bg-destructive-soft text-destructive",
        /** In progress. */
        cut: "bg-primary-soft text-primary",
        /** Structural label with no urgency. */
        neutral: "bg-secondary text-muted-foreground",

        // ── aliases kept so existing call sites compile ──
        default: "bg-primary-soft text-primary",
        secondary: "bg-secondary text-muted-foreground",
        outline: "bg-transparent text-muted-foreground shadow-[inset_0_0_0_1px_var(--input)]",
        ghost: "bg-transparent text-muted-foreground",
        link: "bg-transparent text-primary underline-offset-4 hover:underline",
      },
    },
    defaultVariants: {
      variant: "neutral",
    },
  }
)

function Badge({
  className,
  variant = "neutral",
  render,
  ...props
}: useRender.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return useRender({
    defaultTagName: "span",
    props: mergeProps<"span">(
      {
        className: cn(badgeVariants({ variant }), className),
      },
      props
    ),
    render,
    state: {
      slot: "badge",
      variant,
    },
  })
}

/** The dot that leads a status pill. */
function BadgeDot({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn("inline-block size-1.5 shrink-0 rounded-full bg-current", className)}
    />
  )
}

export { Badge, BadgeDot, badgeVariants }
