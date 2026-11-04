"use client";

import { Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { FieldDef } from "@/types";

function humanize(name: string) {
  return name
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function FixedDocumentValues({
  fields,
  values,
  onChange,
}: {
  fields: FieldDef[];
  values: Record<string, unknown>;
  onChange: (values: Record<string, unknown>) => void;
}) {
  const documentFields = fields.filter((field) => field.scope === "document");
  const unused = documentFields.filter((field) => !(field.name in values));

  function parseValue(field: FieldDef | undefined, raw: string) {
    if (!field || !["number", "currency", "integer"].includes(field.type)) return raw;
    if (!raw.trim()) return "";
    const number = Number(raw);
    return Number.isFinite(number) ? number : raw;
  }

  return (
    <div className="space-y-3">
      <div className="rounded-2xl bg-warning-soft shadow-[inset_0_0_0_1px_#f3e3a0] p-3 text-sm text-muted-foreground">
        Fixed values replace extracted document values. Use them only for values that are genuinely identical on every document for this profile.
      </div>
      {Object.entries(values).map(([name, value]) => {
        const field = documentFields.find((item) => item.name === name);
        return (
          <div key={name} className="grid items-center gap-2 rounded-2xl p-3 shadow-[inset_0_0_0_1px_var(--input)] md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_auto]">
            <div><p className="text-sm font-medium">{humanize(name)}</p><p className="font-mono text-xs text-muted-foreground">field.{name}</p></div>
            <Input type={field?.type === "date" ? "date" : ["number", "currency", "integer"].includes(field?.type ?? "") ? "number" : "text"} value={String(value ?? "")} onChange={(event) => onChange({ ...values, [name]: parseValue(field, event.target.value) })} />
            <Button variant="ghost" size="sm" onClick={() => { const next = { ...values }; delete next[name]; onChange(next); }}><Trash2 className="h-4 w-4" /><span className="sr-only">Remove {name}</span></Button>
          </div>
        );
      })}
      {unused.length > 0 && (
        <Select value={undefined} onValueChange={(name) => name && onChange({ ...values, [name]: "" })}>
          <SelectTrigger className="w-full"><SelectValue placeholder="Add a fixed document field" /></SelectTrigger>
          <SelectContent>{unused.map((field) => <SelectItem key={field.name} value={field.name}>{humanize(field.name)}</SelectItem>)}</SelectContent>
        </Select>
      )}
    </div>
  );
}

function recordOf(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

export function GeneratedProfileDetails({
  extractionPlan,
  evidence,
}: {
  extractionPlan: Record<string, unknown> | null | undefined;
  evidence: {
    evidence_level: string;
    status: "verified" | "review_required" | "failed";
    category_confidence: number;
    metrics: Record<string, unknown>;
    unresolved_risks: string[];
    hard_blockers?: string[];
    review_warnings?: string[];
    engine_version: string;
  } | null | undefined;
}) {
  const plan = recordOf(extractionPlan);
  const regions = Array.isArray(plan.regions) ? plan.regions.map(recordOf) : [];
  const rowSelector = recordOf(plan.row_selector);
  const documentRules = Object.keys(recordOf(plan.document_field_rules));
  const rowRules = Object.keys(recordOf(plan.row_field_rules));
  const reconciliationRules = Array.isArray(plan.reconciliation_rules)
    ? plan.reconciliation_rules.map(recordOf)
    : [];
  const contextRules = Array.isArray(plan.row_context_rules)
    ? plan.row_context_rules.map(recordOf)
    : [];
  return (
    <div className="space-y-4">
      <div className="rounded-lg border p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div><p className="font-medium">Generated extraction plan</p><p className="text-xs text-muted-foreground">Created by profile authoring and used by the extraction engine.</p></div>
          {Object.keys(plan).length > 0 ? <Badge variant="secondary">Version {String(plan.version ?? "1.0")}</Badge> : <Badge variant="outline">Not generated</Badge>}
        </div>
        {Object.keys(plan).length > 0 && (
          <div className="mt-4 grid gap-3 text-sm md:grid-cols-2">
            <div><p className="text-xs text-muted-foreground">Document family</p><p>{String(plan.document_family ?? "standard")}</p></div>
            <div><p className="text-xs text-muted-foreground">Row selection</p><p>{String(rowSelector.scope ?? "row")}</p></div>
            <div><p className="text-xs text-muted-foreground">Regions</p><p>{regions.map((region) => String(region.name ?? "line_items")).join(", ") || "None"}</p></div>
            <div><p className="text-xs text-muted-foreground">Reconciliation rules</p><p>{reconciliationRules.map((rule) => String(rule.name ?? "rule")).join(", ") || "None"}</p></div>
            <div><p className="text-xs text-muted-foreground">Document field rules</p><p>{documentRules.join(", ") || "None"}</p></div>
            <div><p className="text-xs text-muted-foreground">Row field rules</p><p>{rowRules.join(", ") || "None"}</p></div>
            <div><p className="text-xs text-muted-foreground">Carried context</p><p>{contextRules.map((rule) => Object.keys(recordOf(rule.field_groups)).join(", ")).filter(Boolean).join("; ") || "None"}</p></div>
          </div>
        )}
      </div>
      <div className="rounded-lg border p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div><p className="font-medium">Authoring evidence</p><p className="text-xs text-muted-foreground">Read-only evidence retained from profile discovery and validation.</p></div>
          {evidence ? <Badge variant={evidence.status === "verified" ? "default" : "secondary"}>{evidence.status.replaceAll("_", " ")}</Badge> : <Badge variant="outline">Not available</Badge>}
        </div>
        {evidence && (
          <div className="mt-4 space-y-3 text-sm">
            <div className="grid gap-3 md:grid-cols-3">
              <div><p className="text-xs text-muted-foreground">Evidence</p><p>{evidence.evidence_level.replaceAll("_", " ")}</p></div>
              <div><p className="text-xs text-muted-foreground">Confidence</p><p>{Math.round(evidence.category_confidence * 100)}%</p></div>
              <div><p className="text-xs text-muted-foreground">Engine</p><p>{evidence.engine_version}</p></div>
            </div>
            {(evidence.hard_blockers ?? []).length > 0 && <div className="rounded-2xl bg-warning-soft shadow-[inset_0_0_0_1px_#f3e3a0] p-3"><p className="font-medium">Validation findings</p><p className="mt-1 text-xs text-muted-foreground">Informational only; these findings do not block saving or production delivery.</p><ul className="mt-2 list-disc pl-5">{evidence.hard_blockers?.map((risk) => <li key={risk}>{risk}</li>)}</ul></div>}
            {evidence.unresolved_risks.length > 0 && <div className="rounded-md bg-warning/12 p-3"><p className="font-medium">Unresolved risks</p><ul className="mt-1 list-disc pl-5">{evidence.unresolved_risks.map((risk) => <li key={risk}>{risk}</li>)}</ul></div>}
            {Object.keys(evidence.metrics).length > 0 && <details><summary className="cursor-pointer text-xs font-medium">Validation metrics</summary><dl className="mt-2 grid gap-2 md:grid-cols-2">{Object.entries(evidence.metrics).map(([key, value]) => <div key={key}><dt className="text-xs text-muted-foreground">{humanize(key)}</dt><dd>{Array.isArray(value) ? stringList(value).join(", ") : String(value)}</dd></div>)}</dl></details>}
          </div>
        )}
      </div>
    </div>
  );
}
