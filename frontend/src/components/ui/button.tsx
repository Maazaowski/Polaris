import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

/**
 * Button — pills, three tiers.
 *
 *   solid    the one black pill on a screen
 *   hairline the beige pill, for every other real action
 *   text     quiet, for inline and tertiary actions
 *
 * Buttons press to 97% and change colour in 100ms, nothing slower. Focus is the
 * 2px ring defined globally so it is identical on every focusable thing.
 *
 * `default`/`outline`/`secondary`/`ghost` are aliases onto the three tiers so
 * existing call sites keep compiling.
 */
const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center gap-1.5 rounded-full border border-transparent text-sm font-medium whitespace-nowrap transition-[background-color,color,transform] duration-100 outline-none select-none active:scale-[0.97] disabled:pointer-events-none disabled:opacity-45 aria-invalid:border-destructive [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        // ── the three tiers ──
        solid: "bg-ink text-ink-foreground hover:bg-black dark:hover:bg-white aria-expanded:bg-black",
        hairline:
          "bg-secondary text-secondary-foreground hover:bg-[#efece6] dark:hover:bg-[#303030] aria-expanded:bg-[#efece6]",
        text:
          "text-body hover:bg-secondary hover:text-foreground aria-expanded:bg-secondary",

        // ── aliases onto the tiers (kept for migration) ──
        default: "bg-ink text-ink-foreground hover:bg-black dark:hover:bg-white aria-expanded:bg-black",
        outline:
          "bg-secondary text-secondary-foreground hover:bg-[#efece6] dark:hover:bg-[#303030] aria-expanded:bg-[#efece6]",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-[#efece6] dark:hover:bg-[#303030] aria-expanded:bg-[#efece6]",
        ghost:
          "text-body hover:bg-secondary hover:text-foreground aria-expanded:bg-secondary",

        // Destructive reads as a quiet red pill until hovered.
        destructive:
          "bg-destructive-soft text-destructive hover:bg-destructive hover:text-destructive-foreground",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-8 px-3.5",
        xs: "h-6 gap-1 px-2 text-xs [&_svg:not([class*='size-'])]:size-3",
        sm: "h-7 gap-1 px-2.5 text-[0.8125rem] [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-10 px-5 text-[15px]",
        xl: "h-12 px-6 text-[17px] tracking-[-0.22px]",
        icon: "size-8",
        "icon-xs": "size-6 [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-7 [&_svg:not([class*='size-'])]:size-3.5",
        "icon-lg": "size-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  render,
  nativeButton,
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  // Call sites pass `render={<Link …/>}` or `render={<a download …/>}` to get a
  // button-styled link. Base UI expects to be told when the rendered element is
  // not a real <button>, otherwise it warns on every render and keeps native
  // button semantics on an anchor. Default that flag from the render prop so no
  // call site has to remember it.
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      render={render}
      nativeButton={nativeButton ?? render === undefined}
      {...props}
    />
  )
}

export { Button, buttonVariants }
