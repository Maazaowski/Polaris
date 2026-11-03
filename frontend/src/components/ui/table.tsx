"use client"

import * as React from "react"

import { cn } from "@/lib/utils"

/**
 * Table — lives inside a beige card.
 *
 *   - The container is the card: beige, inset ring, 24px corners.
 *   - Header is Inter 12px 500, muted, not uppercase. It stays sticky.
 *   - 40px rows with hairline rules; a row turns white on hover.
 *   - Tabular figures throughout; `numeric` right-aligns and monospaces a cell.
 */
function Table({ className, ...props }: React.ComponentProps<"table">) {
  return (
    <div
      data-slot="table-container"
      className="relative w-full overflow-x-auto rounded-3xl bg-card shadow-[inset_0_0_0_1px_var(--ring-card)]"
    >
      <table
        data-slot="table"
        className={cn(
          "w-full caption-bottom border-collapse text-[14px] tracking-[-0.09px] [font-variant-numeric:tabular-nums]",
          className
        )}
        {...props}
      />
    </div>
  )
}

function TableHeader({ className, ...props }: React.ComponentProps<"thead">) {
  return (
    <thead
      data-slot="table-header"
      className={cn("sticky top-0 z-10 bg-card [&_tr]:border-b [&_tr]:border-border", className)}
      {...props}
    />
  )
}

function TableBody({ className, ...props }: React.ComponentProps<"tbody">) {
  return (
    <tbody
      data-slot="table-body"
      className={cn("[&_tr:last-child]:border-0", className)}
      {...props}
    />
  )
}

function TableFooter({ className, ...props }: React.ComponentProps<"tfoot">) {
  return (
    <tfoot
      data-slot="table-footer"
      className={cn(
        "border-t border-border bg-card font-medium [&>tr]:last:border-b-0",
        className
      )}
      {...props}
    />
  )
}

function TableRow({ className, ...props }: React.ComponentProps<"tr">) {
  return (
    <tr
      data-slot="table-row"
      className={cn(
        "border-b border-border transition-colors duration-200 hover:bg-background has-aria-expanded:bg-background data-[state=selected]:bg-primary-soft",
        className
      )}
      {...props}
    />
  )
}

function TableHead({
  className,
  numeric,
  ...props
}: React.ComponentProps<"th"> & { numeric?: boolean }) {
  return (
    <th
      data-slot="table-head"
      scope="col"
      className={cn(
        "h-10 px-4 text-left align-middle text-[12px] font-medium whitespace-nowrap text-muted-foreground first:pl-5 last:pr-5",
        numeric && "text-right",
        className
      )}
      {...props}
    />
  )
}

function TableCell({
  className,
  numeric,
  ...props
}: React.ComponentProps<"td"> & { numeric?: boolean }) {
  return (
    <td
      data-slot="table-cell"
      className={cn(
        "h-11 px-4 align-middle whitespace-nowrap first:pl-5 last:pr-5",
        numeric && "text-right font-mono text-[13px] tracking-normal text-foreground",
        className
      )}
      {...props}
    />
  )
}

function TableCaption({
  className,
  ...props
}: React.ComponentProps<"caption">) {
  return (
    <caption
      data-slot="table-caption"
      className={cn("mt-3 text-left text-xs text-muted-foreground", className)}
      {...props}
    />
  )
}

export {
  Table,
  TableHeader,
  TableBody,
  TableFooter,
  TableHead,
  TableRow,
  TableCell,
  TableCaption,
}
