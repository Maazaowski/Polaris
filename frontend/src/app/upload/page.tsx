"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { useDropzone } from "react-dropzone";
import { safeFormatDate } from "@/lib/format-date";
import { toast } from "sonner";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  FileText,
  Loader2,
  Upload,
  X,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useUploadInvoice, useInvoices } from "@/hooks/use-invoices";
import { PipelineProgress } from "@/components/pipeline-progress";
import { StatusBadge } from "@/components/status-badge";
import { PageHeader } from "@/components/page-header";
import { Confetti, Mascot } from "@/components/brand/mascot";
import { cn } from "@/lib/utils";

interface QueueItem {
  id: string;
  file: File;
  status: "pending" | "uploading" | "success" | "error";
  message?: string;
  intakeId?: string;
}

export default function UploadPage() {
  const router = useRouter();
  const uploadInvoice = useUploadInvoice();
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [isUploading, setIsUploading] = useState(false);

  const { data: recentData } = useInvoices({ page: 1, per_page: 10 });

  const processingIntakeIds = queue
    .filter((item) => item.status === "success" && item.intakeId)
    .map((item) => item.intakeId as string);

  const onDrop = useCallback(
    (acceptedFiles: File[], rejectedFiles: { file: File }[]) => {
      if (rejectedFiles.length > 0) {
        toast.error("Only PDF files are accepted.");
      }
      const newItems: QueueItem[] = acceptedFiles.map((file) => ({
        id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
        file,
        status: "pending",
      }));
      setQueue((prev) => [...prev, ...newItems]);
    },
    []
  );

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    accept: { "application/pdf": [".pdf"] },
    multiple: true,
    noClick: true,
    maxSize: 50 * 1024 * 1024,
    onDrop,
  });

  function removeFromQueue(id: string) {
    setQueue((prev) => prev.filter((item) => item.id !== id));
  }

  function clearCompleted() {
    setQueue((prev) =>
      prev.filter((item) => item.status !== "success" && item.status !== "error")
    );
  }

  async function uploadAll() {
    const pending = queue.filter((item) => item.status === "pending");
    if (pending.length === 0) return;

    setIsUploading(true);
    let uploadedCount = 0;

    for (const item of pending) {
      setQueue((prev) =>
        prev.map((q) =>
          q.id === item.id ? { ...q, status: "uploading" } : q
        )
      );

      try {
        const result = await uploadInvoice.mutateAsync(item.file);
        setQueue((prev) =>
          prev.map((q) =>
            q.id === item.id
              ? {
                  ...q,
                  status: "success",
                  message: `Queued - ${result.status}`,
                  intakeId: result.id,
                }
              : q
          )
        );
        uploadedCount += 1;
      } catch {
        setQueue((prev) =>
          prev.map((q) =>
            q.id === item.id
              ? {
                  ...q,
                  status: "error",
                  message: "Upload failed",
                }
              : q
          )
        );
      }
    }

    setIsUploading(false);

    if (uploadedCount > 0) {
      toast.success(
        `${uploadedCount} invoice${uploadedCount > 1 ? "s" : ""} queued for processing.`
      );
    }
  }

  const pendingCount = queue.filter((q) => q.status === "pending").length;
  const hasCompleted = queue.some(
    (q) => q.status === "success" || q.status === "error"
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Upload"
        description="Drop PDFs. Polaris names the supplier, picks the template, and gets to work."
      />

      <div
        {...getRootProps()}
        className={cn(
          "fade-up fade-up-1 relative flex min-h-[380px] cursor-pointer flex-col items-center justify-center gap-4 overflow-hidden rounded-4xl bg-card p-8 text-center shadow-[inset_0_0_0_1px_var(--ring-card)] transition-[box-shadow,background-color] duration-200",
          isDragActive
            ? "bg-primary-soft shadow-[inset_0_0_0_2px_var(--primary)]"
            : "hover:shadow-[inset_0_0_0_2px_var(--primary)]"
        )}
        onClick={open}
      >
        <input {...getInputProps()} aria-label="Choose invoice PDFs to upload" />
        <Confetti className="absolute top-8 left-10 h-44 w-44" />
        <Confetti className="absolute right-10 bottom-6 h-44 w-44" flip />
        <Mascot size={140} />
        {isDragActive ? (
          <p className="font-display text-[34px] leading-tight font-semibold tracking-[-0.03em] text-primary">
            Drop them here
          </p>
        ) : (
          <>
            <p className="font-display text-[34px] leading-tight font-semibold tracking-[-0.03em] text-foreground">
              Drop invoices here
            </p>
            <p className="max-w-[380px] text-muted-foreground">
              PDF only, up to 50 MB each, as many as you like. Or{" "}
              <span className="font-medium text-primary">browse your files</span>.
            </p>
            <span className="mt-1 inline-flex h-12 items-center rounded-full bg-ink px-6 text-[17px] font-medium tracking-[-0.22px] text-ink-foreground">
              <Upload className="mr-2 h-4 w-4" aria-hidden="true" />
              Choose PDFs
            </span>
          </>
        )}
      </div>

      {queue.length > 0 && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-3">
            <CardTitle>
              Ready to upload · {queue.length} file{queue.length !== 1 ? "s" : ""}
            </CardTitle>
            <div className="flex gap-2">
              {hasCompleted && (
                <Button variant="ghost" size="sm" onClick={clearCompleted}>
                  Clear completed
                </Button>
              )}
              {pendingCount > 0 && (
                <Button size="sm" onClick={uploadAll} disabled={isUploading}>
                  {isUploading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Upload className="h-4 w-4" />
                  )}
                  Upload {pendingCount} file{pendingCount !== 1 ? "s" : ""}
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {queue.map((item) => (
                <div
                  key={item.id}
                  className="flex items-center gap-3 rounded-2xl bg-background px-4 py-3 shadow-[inset_0_0_0_1px_var(--input)]"
                >
                  {item.status === "uploading" && (
                    <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" />
                  )}
                  {item.status === "success" && (
                    <CheckCircle2 className="h-4 w-4 shrink-0 text-success" />
                  )}
                  {item.status === "error" && (
                    <AlertTriangle className="h-4 w-4 shrink-0 text-destructive" />
                  )}
                  {item.status === "pending" && (
                    <Clock className="h-4 w-4 shrink-0 text-muted-foreground" />
                  )}

                  <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">
                      {item.file.name}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {(item.file.size / 1024 / 1024).toFixed(2)} MB
                      {item.message && <span className="ml-2">- {item.message}</span>}
                    </p>
                  </div>

                  {item.status === "pending" && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      onClick={() => removeFromQueue(item.id)}
                    >
                      <X className="h-3 w-3" />
                    </Button>
                  )}
                  {item.status === "success" && item.intakeId && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => router.push(`/invoices/${item.intakeId}`)}
                    >
                      View
                    </Button>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {processingIntakeIds.length > 0 && (
        <div className="space-y-4">
          <h3 className="text-sm font-medium text-muted-foreground">
            Processing progress
          </h3>
          {processingIntakeIds.map((id) => (
            <PipelineProgress key={id} intakeId={id} />
          ))}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Recent invoices</CardTitle>
        </CardHeader>
        <CardContent>
          {recentData?.items && recentData.items.length > 0 ? (
            <div className="space-y-2">
              {recentData.items.map((invoice) => (
                <div
                  key={invoice.id}
                  className="flex cursor-pointer items-center gap-3 rounded-2xl px-4 py-3 shadow-[inset_0_0_0_1px_var(--input)] transition-colors hover:bg-background"
                  onClick={() => router.push(`/invoices/${invoice.id}`)}
                >
                  <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">
                      {invoice.original_filename}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {safeFormatDate(invoice.created_at, "MMM d, yyyy HH:mm")}
                      {" - "}
                      {invoice.page_count} page
                      {invoice.page_count !== 1 ? "s" : ""}
                    </p>
                  </div>
                  <StatusBadge status={invoice.status} />
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              No invoices yet. Upload a PDF to get started.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
