"use client"

import { Switch as SwitchPrimitive } from "@base-ui/react/switch"

import { cn } from "@/lib/utils"

/**
 * Switch — the iOS shape. Green when on, 250ms spring on the thumb.
 */
function Switch({
  className,
  size = "default",
  ...props
}: SwitchPrimitive.Root.Props & {
  size?: "sm" | "default"
}) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      data-size={size}
      className={cn(
        "peer group/switch relative inline-flex shrink-0 items-center rounded-full border border-transparent transition-colors duration-200 outline-none after:absolute after:-inset-x-3 after:-inset-y-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring aria-invalid:border-destructive data-[size=default]:h-[26px] data-[size=default]:w-[44px] data-[size=sm]:h-[18px] data-[size=sm]:w-[30px] data-checked:bg-[#00c454] data-unchecked:bg-border-strong data-disabled:cursor-not-allowed data-disabled:opacity-50",
        className
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        data-slot="switch-thumb"
        className="pointer-events-none block rounded-full bg-white shadow-[0_1px_4px_rgba(0,0,0,0.2)] transition-transform duration-250 ease-out-expo group-data-[size=default]/switch:size-[22px] group-data-[size=sm]/switch:size-[14px] group-data-[size=default]/switch:data-checked:translate-x-[19px] group-data-[size=sm]/switch:data-checked:translate-x-[13px] group-data-[size=default]/switch:data-unchecked:translate-x-[1px] group-data-[size=sm]/switch:data-unchecked:translate-x-[1px]"
      />
    </SwitchPrimitive.Root>
  )
}

export { Switch }
