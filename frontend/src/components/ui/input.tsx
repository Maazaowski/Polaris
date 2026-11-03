import * as React from "react"
import { Input as InputPrimitive } from "@base-ui/react/input"

import { cn } from "@/lib/utils"

/**
 * Input — white, 8px corners, a 1px inset ring that turns ink on focus.
 */
function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <InputPrimitive
      type={type}
      data-slot="input"
      className={cn(
        "h-9 w-full min-w-0 rounded-md border-0 bg-background px-3 py-1 text-[14px] text-foreground shadow-[inset_0_0_0_1px_var(--input)] transition-shadow outline-none file:inline-flex file:h-6 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground hover:shadow-[inset_0_0_0_1px_var(--border-strong)] focus-visible:shadow-[inset_0_0_0_1.5px_var(--ring)] focus-visible:outline-none disabled:pointer-events-none disabled:cursor-not-allowed disabled:bg-muted disabled:opacity-60 aria-invalid:shadow-[inset_0_0_0_1.5px_var(--destructive)]",
        className
      )}
      {...props}
    />
  )
}

export { Input }
