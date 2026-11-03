"use client";

import { use, useState } from "react";
import Link from "next/link";
import {
  useInvoice,
  useInvoicePreview,
  useInvoiceProvenance,
  useRejectInvoice,
  useCancelInvoice,
} from "@/hooks/use-invoices";
import { ExtractionPreviewView } from "@/components/extraction-preview";
import { ProvenancePanel, type ProvenanceSelection } from "@/components/provenance-panel";
import { ReconciliationPanel } from "@/components/reconciliation-panel";
import { safeFormatDate } from "@/lib/format-date";
import { resolveXlsxOutputFilename } from "@/lib/output-naming";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/states";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  StatusBadge,
  ExtractionPathBadge,
  ReconciliationBadge,
} from "@/components/status-badge";
import { ProcessingTimeline } from "@/components/processing-timeline";
import { useConfirm } from "@/components/ui/confirm-dialog";
import {
  ArrowLeft,
  FileText,
  Download,
  DollarSign,
  Cpu,
  AlertTriangle,
  CheckCircle2,
  Ban,
  FileSearch,
} from "lucide-react";
import type { ExtractionJob } from "@/types";

export default function InvoiceDetailPage({
  params,
}: {
  params: Promise<{ intakeId: string }>;
}) {
  const { intakeId } = use(params);
  const { data: invoice, isLoading, isError } = useInvoice(intakeId);
  const rejectInvoice = useRejectInvoice();
  const cancelInvoice = useCancelInvoice();
  // "Show on PDF": where each delivered value was read from.
  const [showPdf, setShowPdf] = useState(false);
  const [selection, setSelection] = useState<ProvenanceSelection>(null);
  const { data: provenance } = useInvoiceProvenance(
    intakeId,
    invoice?.status === "completed" || invoice?.status === "completed_with_warnings",
  );
  const confirm = useConfirm();
  const { data: preview } = useInvoicePreview(
    intakeId,
    invoice?.status === "completed" ||
      invoice?.status === "completed_with_warnings",
  );

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <div className="grid gap-4 md:grid-cols-2">
          <Skeleton className="h-48" />
          <Skeleton className="h-48" />
        </div>
      </div>
    );
  }

  if (isError || !invoice) {
    return (
      <div className="space-y-6">
        <Button variant="hairline" size="sm" render={<Link href="/invoices" />}>
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Back to the queue
        </Button>
        <ErrorState what="this invoice" />
      </div>
    );
  }

  const job: ExtractionJob | undefined = invoice.jobs?.[0];
  const xlsxFilename = resolveXlsxOutputFilename(
    job?.xlsx_output_filename,
    invoice.original_filename,
  );

  const isModelExtracted = job?.extraction_path === "model" || job?.extraction_path === "model_fallback_ai";
  const isDelivered = invoice.status === "completed" || invoice.status === "completed_with_warnings";
  const canReject = isDelivered && isModelExtracted;
  const isProcessing = invoice.status === "processing" || invoice.status === "received";
  const trainingIncomplete =
    invoice.intake_source === "training" &&
    invoice.status === "completed_with_warnings" &&
    invoice.logs?.some(
      (log) =>
        (log.step === "model_generation" && log.status === "failed") ||
        (log.step === "model_training" && log.status === "failed") ||
        (log.step === "model_validation" && log.status === "failed"),
    );

  async function handleCancel() {
    const ok = await confirm({
      title: "Cancel processing for this invoice?",
      confirmLabel: "Cancel processing",
      variant: "destructive",
    });
    if (!ok) return;
    cancelInvoice.mutate(intakeId, {
      onSuccess: () => toast.success("Processing cancelled."),
      onError: () => toast.error("Failed to cancel processing."),
    });
  }

  async function handleReject() {
    const ok = await confirm({
      title: "Reject this extraction and regenerate via AI?",
      description:
        "This will retire the extraction model that produced this output and re-process the invoice using AI.",
      confirmLabel: "Reject & re-process",
      variant: "destructive",
    });
    if (!ok) return;
    rejectInvoice.mutate(intakeId, {
      onSuccess: () => toast.success("Invoice rejected. Re-processing via AI..."),
      onError: () => toast.error("Failed to reject invoice"),
    });
  }

  return (
    <div className="space-y-6">
      <Link
        href="/invoices"
        className="fade-up inline-flex items-center gap-1.5 text-[14px] text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
        Queue
      </Link>

      {/* Header */}
      <div className="fade-up flex flex-wrap items-end justify-between gap-4">
        <div className="flex min-w-0 flex-col gap-1.5">
          <span className="eyebrow text-section-work">
            {job?.supplier_name ?? "Unknown supplier"}
          </span>
          <h1 className="min-w-0 truncate font-mono text-[26px] leading-tight font-medium text-foreground">
            {invoice.original_filename}
          </h1>
          <div className="flex flex-wrap items-center gap-2 text-[13px] text-muted-foreground">
            <StatusBadge status={invoice.status} />
            {job?.extraction_path && <ExtractionPathBadge path={job.extraction_path} />}
            {invoice.intake_source && (
              <Badge variant="neutral" className="capitalize">{invoice.intake_source}</Badge>
            )}
            <span className="font-mono">{invoice.id}</span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {isProcessing && (
            <Button
              variant="hairline"
              onClick={handleCancel}
              disabled={cancelInvoice.isPending}
            >
              <Ban className="h-4 w-4" aria-hidden="true" />
              {cancelInvoice.isPending ? "Cancelling…" : "Cancel"}
            </Button>
          )}
          {isDelivered && (
            <>
              {canReject && (
                <Button
                  variant="destructive"
                  onClick={handleReject}
                  disabled={rejectInvoice.isPending}
                >
                  <AlertTriangle className="h-4 w-4" aria-hidden="true" />
                  {rejectInvoice.isPending ? "Rejecting…" : "Reject and re-read"}
                </Button>
              )}
              <Button
                variant="hairline"
                render={
                  <a
                    href={`/api/v1/invoices/${invoice.id}/output/canonical_invoice.json`}
                    download="canonical_invoice.json"
                  />
                }
              >
                <Download className="h-4 w-4" aria-hidden="true" />
                JSON
              </Button>
              <Button
                variant="solid"
                render={
                  <a
                    href={`/api/v1/invoices/${invoice.id}/output/${encodeURIComponent(xlsxFilename)}`}
                    download={xlsxFilename}
                  />
                }
              >
                <Download className="h-4 w-4" aria-hidden="true" />
                Download XLSX
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Verdict: the one floating callout on the page. */}
      {isDelivered && job && (
        <div className="fade-up fade-up-1 flex flex-wrap items-center gap-3">
          <span className="inline-flex h-11 items-center gap-2.5 rounded-full bg-background pr-5 pl-3.5 text-[15px] font-medium text-foreground shadow-[var(--shadow-overlay)]">
            <span
              aria-hidden="true"
              className={
                job.is_reconciled
                  ? "flex h-[22px] w-[22px] items-center justify-center rounded-full bg-[#00c454] text-[12px] font-semibold text-white"
                  : "flex h-[22px] w-[22px] items-center justify-center rounded-full bg-warning text-[12px] font-semibold text-white"
              }
            >
              {job.is_reconciled ? "✓" : "!"}
            </span>
            {job.is_reconciled
              ? "Balanced to the printed total"
              : invoice.status === "completed_with_warnings"
                ? invoice.error_message || "Delivered, but a check needs review"
                : "Rows do not sum to the printed total"}
          </span>
          <span className="text-[13px] text-muted-foreground">
            {job.extraction_path === "model"
              ? `Read by template in ${(job.extraction_duration_ms / 1000).toFixed(1)} s · no AI used`
              : `Read with AI in ${(job.extraction_duration_ms / 1000).toFixed(1)} s · $${job.estimated_cost_usd.toFixed(2)}`}
          </span>
        </div>
      )}

      {/*
        Reconciliation FIRST. The operator's task here is "find the row that is
        wrong", so the arithmetic leads and everything else supports it.
      */}
      {isDelivered && preview?.reconciliation && (
        <ReconciliationPanel
          reconciliation={preview.reconciliation}
          lineItemCount={preview.line_item_count}
        />
      )}

      {/* The delivered rows — where the wrong one actually lives. */}
      {isDelivered && preview && (
        <section className="fade-up fade-up-2 flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-[19px] font-medium tracking-[-0.3px] text-foreground">Delivered rows</h2>
            <Button
              size="sm"
              variant="hairline"
              className="ml-auto"
              aria-pressed={showPdf}
              disabled={!provenance?.available}
              title={
                provenance && !provenance.available
                  ? provenance.reason
                  : "Highlight where each delivered value was read from on the PDF"
              }
              onClick={() => setShowPdf((v) => !v)}
            >
              <FileSearch className="h-4 w-4" />
              {showPdf ? "Hide PDF" : "Show on PDF"}
            </Button>
          </div>
          {provenance && !provenance.available && (
            <p className="text-xs text-muted-foreground">{provenance.reason}</p>
          )}
          <ExtractionPreviewView
            preview={preview}
            hideReconciliation
            selectedRow={selection?.kind === "row" ? selection.index : null}
            onLocateRow={
              provenance?.available
                ? (index) => {
                    setSelection((current) =>
                      current?.kind === "row" && current.index === index ? null : { kind: "row", index },
                    );
                    setShowPdf(true);
                  }
                : undefined
            }
          />
          {showPdf && provenance?.available && (
            <ProvenancePanel
              intakeId={intakeId}
              provenance={provenance}
              selection={selection}
              onSelect={setSelection}
            />
          )}
        </section>
      )}

      {/*
        The processing log is diagnostic, not the task. Collapsed by default —
        it used to occupy the top of the page above the actual output. Stays
        open while the invoice is still running, when it IS the task.
      */}
      <details
        className="group/log overflow-hidden rounded-3xl bg-card shadow-[inset_0_0_0_1px_var(--ring-card)]"
        open={isProcessing}
      >
        <summary className="flex cursor-pointer items-center gap-2 px-6 py-4 text-[15px] font-medium text-foreground select-none">
          Processing log
          <span className="ml-auto text-[13px] font-normal text-muted-foreground group-open/log:hidden">Show</span>
          <span className="ml-auto hidden text-[13px] font-normal text-muted-foreground group-open/log:inline">Hide</span>
        </summary>
        <div className="border-t border-border px-6 py-4">
          <ProcessingTimeline intakeId={intakeId} showCancel={false} />
        </div>
      </details>

      {/* Info Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card size="sm">
          <CardHeader className="pb-1">
            <CardTitle className="flex items-center gap-2 text-[13px] font-medium text-muted-foreground">
              <FileText className="h-4 w-4" />
              Document
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Pages</span>
              <span>{invoice.page_count}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Size</span>
              <span>{(invoice.file_size_bytes / 1024).toFixed(0)} KB</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Received</span>
              <span>{safeFormatDate(invoice.created_at, "MMM d, HH:mm")}</span>
            </div>
            {job?.started_at && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Started</span>
                <span>{safeFormatDate(job.started_at, "MMM d, HH:mm")}</span>
              </div>
            )}
            {job?.completed_at && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Completed</span>
                <span>{safeFormatDate(job.completed_at, "MMM d, HH:mm")}</span>
              </div>
            )}
          </CardContent>
        </Card>

        {job && (
          <>
            <Card size="sm">
              <CardHeader className="pb-1">
                <CardTitle className="flex items-center gap-2 text-[13px] font-medium text-muted-foreground">
                  <Cpu className="h-4 w-4" />
                  Extraction
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1.5 text-sm">
                <div className="flex justify-between items-center">
                  <span className="text-muted-foreground">Path</span>
                  <ExtractionPathBadge path={job.extraction_path} />
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-muted-foreground">Reconciled</span>
                  <ReconciliationBadge
                    isReconciled={job.is_reconciled}
                    variance={job.reconciliation_variance}
                  />
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Line Items</span>
                  <span>{job.line_item_count}</span>
                </div>
                {job.supplier_name && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Supplier</span>
                    <span>{job.supplier_name}</span>
                  </div>
                )}
                {trainingIncomplete && (
                  <p className="text-xs text-warning pt-1 border-t mt-2">
                    AI output delivered; model training did not complete. See
                    processing log for comparison files.
                  </p>
                )}
              </CardContent>
            </Card>

            <Card size="sm">
              <CardHeader className="pb-1">
                <CardTitle className="flex items-center gap-2 text-[13px] font-medium text-muted-foreground">
                  <DollarSign className="h-4 w-4" />
                  Cost
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1.5 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">AI spend</span>
                  <span className={job.estimated_cost_usd === 0 ? "font-medium text-success" : ""}>
                    {job.estimated_cost_usd === 0 ? "Free" : `$${job.estimated_cost_usd.toFixed(4)}`}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Input Tokens</span>
                  <span>{job.tokens_input.toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Output Tokens</span>
                  <span>{job.tokens_output.toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Duration</span>
                  <span>{(job.extraction_duration_ms / 1000).toFixed(1)}s</span>
                </div>
              </CardContent>
            </Card>

            <Card size="sm">
              <CardHeader className="pb-1">
                <CardTitle className="flex items-center gap-2 text-[13px] font-medium text-muted-foreground">
                  {job.is_reconciled ? (
                    <CheckCircle2 className="h-4 w-4 text-success" />
                  ) : (
                    <AlertTriangle className="h-4 w-4 text-warning" />
                  )}
                  Reconciliation
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1.5 text-sm">
                <div className="flex justify-between items-center">
                  <span className="text-muted-foreground">Status</span>
                  <Badge variant={job.is_reconciled ? "success" : "warning"}>
                    {job.is_reconciled ? "Balanced" : "Variance"}
                  </Badge>
                </div>
                {job.reconciliation_variance !== null && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Variance</span>
                    <span>
                      {(job.reconciliation_variance * 100).toFixed(1)}%
                    </span>
                  </div>
                )}
                <div className="flex justify-between">
                  <span className="text-muted-foreground">
                    {job.extraction_path === "model" ? "Template" : "Model"}
                  </span>
                  <span className="text-xs font-mono">
                    {job.extraction_path === "model"
                      ? job.extraction_model_id ?? "—"
                      : job.ai_model_name ?? "—"}
                  </span>
                </div>
              </CardContent>
            </Card>
          </>
        )}
      </div>

      {/* Tabs: Errors only — timeline is shown above */}
      {job?.error_message && (
        <Tabs defaultValue="errors">
          <TabsList>
            <TabsTrigger value="errors">Errors</TabsTrigger>
          </TabsList>
          <TabsContent value="errors" className="mt-4">
            <Card className="bg-destructive-soft shadow-[inset_0_0_0_1px_#ffd9d9]">
              <CardContent>
                <pre className="text-xs text-destructive whitespace-pre-wrap font-mono">
                  {job.error_message}
                </pre>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}
