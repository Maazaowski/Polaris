"use client";

import { useRouter } from "next/navigation";
import {
  useExceptions,
  useRetryException,
  useResolveException,
} from "@/hooks/use-exceptions";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge, BadgeDot } from "@/components/ui/badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { toast } from "sonner";
import { format } from "date-fns";
import { RefreshCw, CheckCircle2, ExternalLink } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { usePrompt } from "@/components/ui/confirm-dialog";
import type { ExceptionRecord } from "@/types";

const reasonTone: Record<string, "warning" | "destructive" | "neutral"> = {
  low_confidence: "warning",
  reconciliation_failure: "destructive",
  schema_validation: "destructive",
  extraction_error: "destructive",
  unknown_supplier: "neutral",
  unreadable_pdf: "neutral",
};

function formatReason(reason: string): string {
  return reason
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function ExceptionsPage() {
  const router = useRouter();
  const { data: exceptions, isLoading, isError, refetch } = useExceptions();
  const retryException = useRetryException();
  const resolveException = useResolveException();
  const prompt = usePrompt();

  async function handleRetry(intakeId: string) {
    try {
      await retryException.mutateAsync(intakeId);
      toast.success("Invoice queued for reprocessing.");
    } catch {
      toast.error("Failed to retry.");
    }
  }

  async function handleResolve(intakeId: string) {
    const notes = await prompt({
      title: "Resolve exception",
      description: "Add optional resolution notes for the record.",
      placeholder: "Resolution notes (optional)",
      confirmLabel: "Resolve",
      multiline: true,
    });
    if (notes === null) return; // cancelled
    try {
      await resolveException.mutateAsync({ intakeId, notes: notes || undefined });
      toast.success("Exception resolved.");
    } catch {
      toast.error("Failed to resolve exception.");
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Needs you"
        description="What Polaris could not settle on its own. Each card says why, and what fixes it."
      />

      {isLoading ? (
        <LoadingState rows={4} />
      ) : isError ? (
        <ErrorState what="the review list" onRetry={() => refetch()} />
      ) : !exceptions || exceptions.length === 0 ? (
        <EmptyState
          tone="green"
          title="Everything ran on its own."
          hint="Nothing is waiting on a person. The queue is clear."
          action={
            <Button variant="hairline" onClick={() => router.push("/invoices")}>
              Back to the queue
            </Button>
          }
        />
      ) : (
        <div className="fade-up fade-up-1 space-y-4">
          {exceptions.map((exc: ExceptionRecord) => (
            <Card key={exc.intake_id} className="py-0">
              <div className="grid md:grid-cols-[minmax(0,1fr)_280px]">
                {/* Why */}
                <div className="flex min-w-0 flex-col gap-3 px-6 py-5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-[13px] text-foreground">
                      {exc.original_filename ?? exc.intake_id.slice(0, 12)}
                    </span>
                    <Badge variant={reasonTone[exc.reason] ?? "destructive"}>
                      <BadgeDot />
                      {formatReason(exc.reason)}
                    </Badge>
                    {exc.status && <Badge variant="neutral">{exc.status.replace(/_/g, " ")}</Badge>}
                    {exc.timestamp && (
                      <span className="ml-auto text-[13px] text-muted-foreground">
                        {format(new Date(exc.timestamp), "d MMM, HH:mm")}
                      </span>
                    )}
                  </div>

                  {exc.message && (
                    <p className="text-[17px] leading-snug font-medium tracking-[-0.2px] text-foreground">
                      {exc.message}
                    </p>
                  )}

                  <span className="font-mono text-[12px] text-muted-foreground">
                    {exc.intake_id}
                  </span>
                </div>

                {/* Fix */}
                <div className="flex flex-col gap-2 border-t border-ring-card bg-background px-6 py-5 md:border-t-0 md:border-l">
                  <span className="eyebrow text-section-system">Fix it</span>
                  <Button
                    variant="solid"
                    className="justify-start"
                    onClick={() => router.push(`/invoices/${exc.intake_id}`)}
                  >
                    <ExternalLink className="h-4 w-4" aria-hidden="true" />
                    Open the invoice
                  </Button>
                  <Button
                    variant="hairline"
                    className="justify-start"
                    onClick={() => handleRetry(exc.intake_id)}
                    disabled={retryException.isPending}
                  >
                    <RefreshCw className="h-4 w-4" aria-hidden="true" />
                    Run it again
                  </Button>
                  <Button
                    variant="hairline"
                    className="justify-start"
                    onClick={() => handleResolve(exc.intake_id)}
                    disabled={resolveException.isPending}
                  >
                    <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                    Mark resolved
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
