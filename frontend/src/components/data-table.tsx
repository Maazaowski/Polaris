"use client";

import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
  getSortedRowModel,
  type SortingState,
} from "@tanstack/react-table";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { ArrowUpDown, ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";

interface DataTableProps<TData, TValue> {
  columns: ColumnDef<TData, TValue>[];
  data: TData[];
  page?: number;
  totalPages?: number;
  onPageChange?: (page: number) => void;
  onRowClick?: (row: TData) => void;
  emptyState?: React.ReactNode;
  /**
   * Phone rendering for a single record. When supplied, widths below `md` swap
   * the table for a stacked list.
   */
  mobileRow?: (row: TData) => React.ReactNode;
}

export function DataTable<TData, TValue>({
  columns,
  data,
  page = 1,
  totalPages = 1,
  onPageChange,
  onRowClick,
  emptyState,
  mobileRow,
}: DataTableProps<TData, TValue>) {
  const [sorting, setSorting] = useState<SortingState>([]);

  // eslint-disable-next-line react-hooks/incompatible-library -- TanStack Table returns unstable function refs by design
  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    onSortingChange: setSorting,
    state: { sorting },
  });

  const hasRows = table.getRowModel().rows.length > 0;

  return (
    <div className="space-y-4">
      <div className={mobileRow ? "hidden md:block" : undefined}>
        {hasRows ? (
          <Table>
            <TableHeader>
              {table.getHeaderGroups().map((headerGroup) => (
                <TableRow key={headerGroup.id} className="hover:bg-transparent">
                  {headerGroup.headers.map((header) => (
                    <TableHead key={header.id}>
                      {header.isPlaceholder
                        ? null
                        : flexRender(
                            header.column.columnDef.header,
                            header.getContext()
                          )}
                    </TableHead>
                  ))}
                </TableRow>
              ))}
            </TableHeader>
            <TableBody>
              {table.getRowModel().rows.map((row) => (
                <TableRow
                  key={row.id}
                  className={onRowClick ? "cursor-pointer" : ""}
                  onClick={() => onRowClick?.(row.original)}
                >
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext()
                      )}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <div>{emptyState ?? <p className="py-8 text-center text-muted-foreground">No results.</p>}</div>
        )}
      </div>

      {/* Stacked records for phone widths. */}
      {mobileRow && (
        <div className="overflow-hidden rounded-3xl bg-card shadow-[inset_0_0_0_1px_var(--ring-card)] md:hidden">
          {hasRows ? (
            table.getRowModel().rows.map((row) => (
              <button
                key={row.id}
                type="button"
                onClick={() => onRowClick?.(row.original)}
                disabled={!onRowClick}
                className="block w-full border-b border-border px-4 py-3 text-left transition-colors last:border-b-0 enabled:hover:bg-background disabled:cursor-default"
              >
                {mobileRow(row.original)}
              </button>
            ))
          ) : (
            <div className="px-3 py-8 text-center text-muted-foreground">
              {emptyState ?? "No results."}
            </div>
          )}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && onPageChange && (
        <div className="flex items-center justify-between px-1">
          <p className="text-[13px] text-muted-foreground">
            Page {page} of {totalPages}
          </p>
          <div className="flex items-center gap-1.5">
            <Button
              variant="hairline"
              size="sm"
              onClick={() => onPageChange(page - 1)}
              disabled={page <= 1}
            >
              <ChevronLeft className="h-4 w-4" />
              Previous
            </Button>
            <Button
              variant="hairline"
              size="sm"
              onClick={() => onPageChange(page + 1)}
              disabled={page >= totalPages}
            >
              Next
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// Helper for sortable column headers
export function SortableHeader({
  column,
  label,
}: {
  column: { toggleSorting: (desc?: boolean) => void; getIsSorted: () => false | "asc" | "desc" };
  label: string;
}) {
  return (
    <button
      type="button"
      className="-ml-1 inline-flex h-7 items-center gap-1 rounded-full px-1 text-[12px] font-medium text-muted-foreground transition-colors hover:text-foreground"
      onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
    >
      {label}
      <ArrowUpDown className="h-3 w-3" aria-hidden="true" />
    </button>
  );
}
