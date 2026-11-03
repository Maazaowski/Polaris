"use client";

import { useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { LayoutCanvas, useCanvasGeometry } from "@/components/builder/layout-canvas";
import { useIntakeLayout, type LayoutPage } from "@/hooks/use-builder";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { InvoiceProvenance, ProvenanceBox, ProvenanceLabelValue, ProvenanceRow } from "@/types";

/** What the operator is pointing at: a delivered row, or a header field / total. */
export type ProvenanceSelection =
  | { kind: "row"; index: number }
  | { kind: "header"; name: string }
  | null;

type Tone = "focus" | "field" | "dim";

const TONE_CLASS: Record<Tone, string> = {
  focus: "border-primary bg-primary/15",
  field: "border-warning bg-warning/20",
  dim: "border-primary/30 bg-primary/5",
};

/** One highlighted region, positioned through the canvas geometry. */
function Highlight({ box, tone, title }: { box: ProvenanceBox; tone: Tone; title?: string }) {
  const g = useCanvasGeometry();
  return (
    <div
      aria-hidden="true"
      data-testid={`provenance-box-${tone}`}
      className={cn("pointer-events-none absolute rounded-[2px] border", TONE_CLASS[tone])}
      style={{
        left: g.x(box.x0),
        top: g.y(box.y0),
        width: Math.max(2, g.x(box.x1 - box.x0)),
        height: Math.max(2, g.y(box.y1 - box.y0)),
      }}
      title={title}
    />
  );
}

/** A row named only by id (AI path) is highlighted from the layout's own geometry. */
function rowBox(page: LayoutPage, rowId: string): ProvenanceBox | null {
  const row = page.rows.find((r) => r.row_id === rowId);
  return row?.normalized_bbox ?? null;
}

function humanField(name: string): string {
  return name.replace(/_/g, " ");
}

/**
 * "Show on PDF": the reconstructed page with the regions each delivered value
 * was read from. Reuses the builder canvas, so the geometry is the one the
 * template itself executed against. Rows on the page are tinted faintly; the
 * selected row is outlined, and its per-field boxes (template path only) are
 * marked in the warning colour.
 */
export function ProvenancePanel({
  intakeId,
  provenance,
  selection,
  onSelect,
}: {
  intakeId: string;
  provenance: InvoiceProvenance;
  selection: ProvenanceSelection;
  onSelect: (selection: ProvenanceSelection) => void;
}) {
  const layout = useIntakeLayout(intakeId);
  const rows = provenance.rows ?? [];
  const header = provenance.header ?? {};
  const totals = provenance.totals ?? {};

  const selectedRow: ProvenanceRow | null = selection?.kind === "row" ? (rows[selection.index] ?? null) : null;
  const selectedLabel: ProvenanceLabelValue | null =
    selection?.kind === "header" ? (header[selection.name] ?? totals[selection.name] ?? null) : null;

  // The page follows the selection; paging by hand overrides it until the
  // selection changes again (keyed, so no effect is needed to reset it).
  const selectionKey = JSON.stringify(selection);
  const [manual, setManual] = useState<{ key: string; page: number } | null>(null);
  const targetPage =
    selectedRow?.page ?? selectedLabel?.page ?? rows.find((r) => r.page)?.page ?? provenance.pages?.[0] ?? 1;
  const pageNumber = manual && manual.key === selectionKey ? manual.page : targetPage;

  const pages = layout.data?.pages ?? [];
  const page = pages.find((p) => p.page_number === pageNumber) ?? null;
  const pageCount = layout.data?.page_count ?? pages.length;
  const lastRendered = pages.length ? pages[pages.length - 1].page_number : 1;

  const labelled = Object.entries({ ...header, ...totals }).filter(([, v]) => v && v.page);

  function goTo(next: number) {
    const clamped = Math.max(1, Math.min(lastRendered, next));
    setManual({ key: selectionKey, page: clamped });
  }

  return (
    <section
      aria-label="Where each value was read from on the PDF"
      data-testid="provenance-panel"
      className="flex flex-col gap-3 rounded-3xl bg-card p-5 shadow-[inset_0_0_0_1px_var(--ring-card)]"
    >
      <div className="flex flex-wrap items-center gap-2 text-[13px]">
        <Button
          size="icon-sm"
          variant="outline"
          aria-label="Previous page"
          onClick={() => goTo(pageNumber - 1)}
          disabled={pageNumber <= 1}
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="tabular-nums" aria-live="polite">
          Page {pageNumber} of {pageCount}
        </span>
        <Button
          size="icon-sm"
          variant="outline"
          aria-label="Next page"
          onClick={() => goTo(pageNumber + 1)}
          disabled={pageNumber >= lastRendered}
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
        {selectedRow ? (
          <span className="text-muted-foreground">
            Row {selectedRow.row_index + 1}
            {selectedRow.row_ids.length ? ` · printed row ${selectedRow.row_ids.join(", ")}` : ""}
          </span>
        ) : selectedLabel && selection?.kind === "header" ? (
          <span className="text-muted-foreground">{humanField(selection.name)}</span>
        ) : (
          <span className="text-muted-foreground">Pick a delivered row or a field to locate it.</span>
        )}
        {provenance.approximate && (
          <span className="ml-auto rounded-full bg-warning-soft px-2.5 py-0.5 text-warning">
            Approximate: AI path cites printed rows, not individual cells
          </span>
        )}
      </div>

      {labelled.length > 0 && (
        <div className="flex flex-wrap gap-1" role="group" aria-label="Header fields and totals">
          {labelled.map(([name]) => {
            const active = selection?.kind === "header" && selection.name === name;
            return (
              <button
                key={name}
                type="button"
                aria-pressed={active}
                onClick={() => onSelect(active ? null : { kind: "header", name })}
                className={cn(
                  "h-7 rounded-full px-2.5 text-[13px] font-medium capitalize transition-colors",
                  active ? "bg-ink text-ink-foreground" : "bg-secondary text-body hover:text-foreground",
                )}
              >
                {humanField(name)}
              </button>
            );
          })}
        </div>
      )}

      {layout.isLoading && <Skeleton className="h-[480px] w-full" />}
      {layout.isError && (
        <p className="text-sm text-destructive">The page layout could not be loaded for this invoice.</p>
      )}
      {!layout.isLoading && !layout.isError && !page && (
        <p className="text-sm text-muted-foreground">
          Page {pageNumber} is beyond the {lastRendered} page{lastRendered === 1 ? "" : "s"} rendered for this view.
        </p>
      )}
      {page && (
        <div className="max-h-[70vh] overflow-auto rounded-2xl bg-secondary p-3">
          <LayoutCanvas page={page} zoom={0.8} showRowOutlines={false}>
            {/* Every delivered row on this page, faintly, so the operator sees coverage. */}
            {rows.map((r) =>
              r.page === page.page_number && r !== selectedRow
                ? (r.box ?? (r.row_ids[0] ? rowBox(page, r.row_ids[0]) : null)) && (
                    <Highlight
                      key={`row-${r.row_index}`}
                      box={(r.box ?? rowBox(page, r.row_ids[0]))!}
                      tone="dim"
                      title={`Delivered row ${r.row_index + 1}`}
                    />
                  )
                : null,
            )}
            {selectedRow && selectedRow.page === page.page_number && (
              <>
                {(selectedRow.box ?? (selectedRow.row_ids[0] ? rowBox(page, selectedRow.row_ids[0]) : null)) && (
                  <Highlight
                    box={(selectedRow.box ?? rowBox(page, selectedRow.row_ids[0]))!}
                    tone="focus"
                    title={`Delivered row ${selectedRow.row_index + 1}`}
                  />
                )}
                {Object.entries(selectedRow.fields).map(([name, f]) =>
                  f.box && (f.page ?? selectedRow.page) === page.page_number ? (
                    <Highlight key={`field-${name}`} box={f.box} tone="field" title={humanField(name)} />
                  ) : null,
                )}
              </>
            )}
            {selectedLabel && selectedLabel.page === page.page_number && (
              <>
                {selectedLabel.label_box && <Highlight box={selectedLabel.label_box} tone="dim" title="Label" />}
                {selectedLabel.value_box && <Highlight box={selectedLabel.value_box} tone="focus" title="Value" />}
              </>
            )}
          </LayoutCanvas>
        </div>
      )}
    </section>
  );
}
