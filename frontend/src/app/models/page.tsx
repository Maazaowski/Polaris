"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useModels, useDeleteModel, useBootstrapModel } from "@/hooks/use-models";
import { useProfiles } from "@/hooks/use-profiles";
import { modelDetailPath } from "@/lib/model-routes";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { safeFormatDate } from "@/lib/format-date";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useConfirm } from "@/components/ui/confirm-dialog";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { cn } from "@/lib/utils";
import { ModelStatusBadge, ConfidenceBadge } from "@/components/status-badge";

const STATUS_FILTERS: Array<{ value: string; label: string }> = [
  { value: "", label: "All" },
  { value: "approved", label: "Approved" },
  { value: "candidate", label: "Candidate" },
  { value: "draft", label: "Draft" },
  { value: "failed_validation", label: "Drifted" },
  { value: "retired", label: "Retired" },
];
import { DataTable, SortableHeader } from "@/components/data-table";
import { PageHeader } from "@/components/page-header";
import { type ColumnDef } from "@tanstack/react-table";
import { Search, Trash2, Plus, Wrench } from "lucide-react";
import { toast } from "sonner";
import type { ExtractionModel } from "@/types";

function NewModelDialog() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const { data: allProfiles } = useProfiles();
  const bootstrap = useBootstrapModel();
  // Any non-retired profile can have a model trained for it (a profile is only
  // "active" AFTER its model is approved — so we can't restrict to active here).
  const profiles = (allProfiles ?? []).filter((p) => p.status !== "retired");

  async function handlePick(profileId: string) {
    try {
      const model = await bootstrap.mutateAsync(profileId);
      setOpen(false);
      router.push(`${modelDetailPath(model.id)}?tab=training`);
    } catch {
      toast.error("Failed to create the model. Does the profile exist?");
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="solid" />}>
        <Plus className="h-4 w-4" aria-hidden="true" />
        New template
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Write a new template</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Pick the supplier this template reads for. You then upload sample invoices and
          Polaris writes and checks the template.
        </p>
        <div className="max-h-72 divide-y divide-border overflow-y-auto rounded-2xl shadow-[inset_0_0_0_1px_var(--input)]">
          {profiles.map((p) => (
            <button
              key={p.profile_id}
              className="flex w-full items-center justify-between gap-2 px-4 py-2.5 text-left text-sm transition-colors hover:bg-secondary disabled:opacity-50"
              disabled={bootstrap.isPending}
              onClick={() => handlePick(p.profile_id)}
            >
              <span>
                <span className="font-medium">{p.identity.canonical_name}</span>{" "}
                <span className="font-mono text-xs text-muted-foreground">{p.profile_id}</span>
              </span>
              <Badge variant="secondary" className="text-xs shrink-0">{p.status}</Badge>
            </button>
          ))}
          {profiles.length === 0 && (
            <p className="px-3 py-3 text-xs text-muted-foreground">
              No supplier profiles yet. Create one on the Profiles page first.
            </p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

const baseColumns: ColumnDef<ExtractionModel>[] = [
  {
    accessorKey: "supplier",
    header: ({ column }) => <SortableHeader column={column} label="Supplier" />,
    cell: ({ row }) => (
      <span className="text-sm font-medium text-foreground">{row.original.supplier}</span>
    ),
  },
  {
    accessorKey: "id",
    header: "Template",
    cell: ({ row }) => (
      <span className="font-mono text-[13px] text-muted-foreground">
        {row.original.id.length > 24
          ? `${row.original.id.slice(0, 24)}…`
          : row.original.id}
      </span>
    ),
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => (
      <span className="inline-flex items-center gap-1">
        <ModelStatusBadge status={row.original.status} />
        {(row.original.profile_missing || row.original.source_intake_missing) && (
          <Badge
            variant="destructive"
            className="text-[10px]"
            title={
              row.original.profile_missing
                ? "The owning profile was deleted; this model can never route."
                : "The authoring invoice was purged; this model cannot be re-keyed or retrained from source."
            }
          >
            Orphaned
          </Badge>
        )}
      </span>
    ),
  },
  {
    accessorKey: "confidence",
    header: "Confidence",
    cell: ({ row }) => (
      <ConfidenceBadge confidence={row.original.confidence} />
    ),
  },
  {
    accessorKey: "times_used",
    header: "Used",
    cell: ({ row }) => (
      <span className="text-sm text-muted-foreground">
        {row.original.times_used}x
      </span>
    ),
  },
  {
    accessorKey: "output_type",
    header: "Type",
    cell: ({ row }) => (
      <Badge variant="neutral">{row.original.output_type.replace(/_/g, " ")}</Badge>
    ),
  },
  {
    accessorKey: "created_by",
    header: "Written by",
    cell: ({ row }) => (
      <span className="text-sm text-muted-foreground">
        {row.original.created_by || "—"}
      </span>
    ),
  },
  {
    accessorKey: "created_at",
    header: ({ column }) => <SortableHeader column={column} label="Created" />,
    cell: ({ row }) => (
      <span className="text-sm text-muted-foreground">
        {safeFormatDate(row.original.created_at, "MMM d, yyyy")}
      </span>
    ),
  },
];

export default function ModelsPage() {
  const router = useRouter();
  const deleteModel = useDeleteModel();
  const confirm = useConfirm();
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const { data, isLoading, isError, refetch } = useModels({
    page,
    per_page: 20,
    status: status || undefined,
    supplier: search || undefined,
  });

  async function handleDelete(model: ExtractionModel, event: React.MouseEvent) {
    event.stopPropagation();
    const ok = await confirm({
      title: `Permanently delete model ${model.id}?`,
      description: "This cannot be undone.",
      confirmLabel: "Delete",
      variant: "destructive",
    });
    if (!ok) return;
    try {
      await deleteModel.mutateAsync(model.id);
      toast.success("Model deleted.");
    } catch {
      toast.error("Failed to delete model.");
    }
  }

  const columns: ColumnDef<ExtractionModel>[] = [
    ...baseColumns,
    {
      id: "actions",
      header: "",
      cell: ({ row }) => (
        <Button
          variant="ghost"
          size="icon-sm"
          className="text-muted-foreground hover:text-destructive"
          disabled={deleteModel.isPending}
          onClick={(event) => handleDelete(row.original, event)}
          title="Delete model"
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Templates"
        description="A template is written once per layout, then reads every later invoice for free."
        actions={
          <>
            <Button variant="hairline" onClick={() => router.push("/models/builder")}>
              <Wrench className="h-4 w-4" aria-hidden="true" />
              Draw one by hand
            </Button>
            <NewModelDialog />
          </>
        }
      />

      {/* Filters */}
      <div className="fade-up fade-up-1 flex flex-wrap items-center gap-2">
        <div role="group" aria-label="Status" className="flex flex-wrap gap-1">
          {STATUS_FILTERS.map((s) => {
            const on = status === s.value;
            return (
              <button
                key={s.value || "all"}
                type="button"
                aria-pressed={on}
                onClick={() => {
                  setStatus(s.value);
                  setPage(1);
                }}
                className={cn(
                  "h-8 rounded-full px-3.5 text-sm font-medium transition-[background-color,color,transform] duration-100 active:scale-[0.97]",
                  on ? "bg-ink text-ink-foreground" : "text-body hover:bg-secondary hover:text-foreground",
                )}
              >
                {s.label}
              </button>
            );
          })}
        </div>
        <div className="relative ml-auto min-w-[14rem] md:max-w-xs">
          <Search className="pointer-events-none absolute top-1/2 left-3 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <Input
            placeholder="Search by supplier…"
            aria-label="Search templates by supplier"
            className="h-9 pl-9"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
        </div>
      </div>

      {/* Table */}
      {isLoading ? (
        <LoadingState rows={6} />
      ) : isError ? (
        <ErrorState what="the templates" onRetry={() => refetch()} />
      ) : (data?.items ?? []).length === 0 && !search && !status ? (
        <EmptyState
          tone="yellow"
          title="No templates yet."
          hint="Pick a supplier and Polaris writes a template from its next invoice. After that, every invoice of that layout runs at $0."
          action={<NewModelDialog />}
        />
      ) : (
        <DataTable
          columns={columns}
          data={data?.items ?? []}
          page={page}
          totalPages={data?.pages ?? 1}
          onPageChange={setPage}
          onRowClick={(model) => router.push(modelDetailPath(model.id))}
        />
      )}

    </div>
  );
}
