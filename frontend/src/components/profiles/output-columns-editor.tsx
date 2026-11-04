"use client";

import { useMemo } from "react";
import { AlertTriangle, ArrowDown, ArrowUp, ChevronDown, Plus, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { humanizeFieldName } from "@/components/profiles/fields-editor";
import type { FieldDef, OutputColumn, OutputTransform } from "@/types";

export const COMPUTED_SOURCES = ["computed.line_tax"];
export const OUTPUT_TRANSFORMS: Array<{ value: OutputTransform; label: string }> = [
  { value: "digits_only", label: "Keep digits only" },
  { value: "trim", label: "Trim spaces" },
  { value: "uppercase", label: "Uppercase" },
  { value: "lowercase", label: "Lowercase" },
];

export function sourcePath(field: Pick<FieldDef, "scope" | "name">): string {
  return `${field.scope === "document" ? "field" : "row"}.${field.name}`;
}

export function SourceSelect({
  id,
  value,
  fields,
  onChange,
  allowNone = false,
  placeholder = "Choose a source",
}: {
  id?: string;
  value: string | null | undefined;
  fields: FieldDef[];
  onChange: (value: string | null) => void;
  allowNone?: boolean;
  placeholder?: string;
}) {
  const documentFields = fields.filter((field) => field.scope === "document");
  const rowFields = fields.filter((field) => field.scope === "row");
  const validPaths = new Set([
    ...documentFields.map((field) => `field.${field.name}`),
    ...rowFields.map((field) => `row.${field.name}`),
    ...COMPUTED_SOURCES,
  ]);
  return (
    <Select
      value={value || (allowNone ? "__none__" : undefined)}
      onValueChange={(next) => onChange(!next || next === "__none__" ? null : next)}
    >
      <SelectTrigger id={id} className="w-full">
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {allowNone && <SelectItem value="__none__">No fallback</SelectItem>}
        {value && !validPaths.has(value) && (
          <SelectItem value={value}>{value} (not a field this profile reads)</SelectItem>
        )}
        {documentFields.length > 0 && (
          <SelectGroup>
            <SelectLabel>Document fields</SelectLabel>
            {documentFields.map((field) => (
              <SelectItem key={`field.${field.name}`} value={`field.${field.name}`}>
                {humanizeFieldName(field.name)} · document
              </SelectItem>
            ))}
          </SelectGroup>
        )}
        {rowFields.length > 0 && (
          <SelectGroup>
            <SelectLabel>Line-item fields</SelectLabel>
            {rowFields.map((field) => (
              <SelectItem key={`row.${field.name}`} value={`row.${field.name}`}>
                {humanizeFieldName(field.name)} · row
              </SelectItem>
            ))}
          </SelectGroup>
        )}
        <SelectGroup>
          <SelectLabel>Computed values</SelectLabel>
          {COMPUTED_SOURCES.map((source) => (
            <SelectItem key={source} value={source}>{humanizeFieldName(source.slice(9))} · computed</SelectItem>
          ))}
        </SelectGroup>
      </SelectContent>
    </Select>
  );
}

export function emptyOutputColumn(): OutputColumn {
  return { header: "", source: "", fallback: null, transforms: [], width: 15, number_format: null };
}

/** Problems the backend would reject at save or activation time, mirrored here
 * so the user sees them while editing. */
export function outputColumnIssues(columns: OutputColumn[], fields: FieldDef[]): string[] {
  const available = new Set([...fields.map(sourcePath), ...COMPUTED_SOURCES]);
  const issues: string[] = [];
  const headers = columns.map((c) => c.header.trim());
  if (headers.some((h) => !h)) issues.push("Every column needs a header.");
  const seen = new Set<string>();
  for (const h of headers) {
    if (h && seen.has(h)) issues.push(`Header "${h}" is used more than once.`);
    seen.add(h);
  }
  for (const column of columns) {
    const label = column.header.trim() || "(unnamed)";
    if (!column.source) issues.push(`${label}: choose a source.`);
    else if (!available.has(column.source)) issues.push(`${label}: ${column.source} is not a field this profile reads.`);
    if (column.fallback && !available.has(column.fallback)) issues.push(`${label}: fallback ${column.fallback} is not available.`);
    const transforms = column.transforms ?? [];
    if (transforms.length && column.source.startsWith("computed.")) issues.push(`${label}: computed values cannot use transforms.`);
    if (transforms.includes("uppercase") && transforms.includes("lowercase")) issues.push(`${label}: uppercase and lowercase cannot be combined.`);
  }
  return Array.from(new Set(issues));
}

export interface OutputColumnsEditorProps {
  columns: OutputColumn[];
  /** The fields that may be delivered (the profile's effective field set). */
  fields: FieldDef[];
  onChange: (columns: OutputColumn[]) => void;
  /** Compact layout for narrow panels (the builder sidebar). */
  compact?: boolean;
  /** Per-header notes to show under a column (the assistant's reasons). */
  reasons?: Record<string, string>;
}

/**
 * The delivered columns, in order. Starts empty: nothing about the deliverable
 * is assumed. Each column names its header, the field it reads from, an
 * optional fallback, delivery transforms and the XLSX formatting.
 */
export function OutputColumnsEditor({ columns, fields, onChange, compact = false, reasons }: OutputColumnsEditorProps) {
  const issues = useMemo(() => outputColumnIssues(columns, fields), [columns, fields]);

  function patch(index: number, update: Partial<OutputColumn>) {
    onChange(columns.map((c, i) => (i === index ? { ...c, ...update } : c)));
  }

  function move(index: number, delta: number) {
    const target = index + delta;
    if (target < 0 || target >= columns.length) return;
    const next = [...columns];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  }

  return (
    <div className="space-y-3">
      {columns.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No columns yet. Nothing is delivered until you add the columns this supplier&apos;s output should carry.
        </p>
      )}
      {issues.length > 0 && columns.length > 0 && (
        <div className="rounded-2xl bg-warning-soft px-3 py-2 text-xs text-warning shadow-[inset_0_0_0_1px_#f3e3a0]">
          <div className="flex items-center gap-2 font-medium"><AlertTriangle className="h-4 w-4" />Columns need attention</div>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">{issues.map((issue) => <li key={issue}>{issue}</li>)}</ul>
        </div>
      )}
      {columns.map((column, index) => {
        const id = `column-${index}`;
        const transforms = column.transforms ?? [];
        return (
          <div key={id} className="rounded-2xl p-3 shadow-[inset_0_0_0_1px_var(--input)]">
            <div className="flex items-center gap-2">
              <Badge variant="outline">{index + 1}</Badge>
              <div className="flex-1 space-y-1">
                <label htmlFor={`${id}-header`} className="sr-only">Header for column {index + 1}</label>
                <Input
                  id={`${id}-header`}
                  value={column.header}
                  onChange={(e) => patch(index, { header: e.target.value })}
                  placeholder="Column header, e.g. INVOICE_NUMBER"
                  className="font-medium"
                />
              </div>
              <Button type="button" variant="ghost" size="icon" onClick={() => move(index, -1)} disabled={index === 0} aria-label={`Move column ${index + 1} up`}>
                <ArrowUp className="h-4 w-4" />
              </Button>
              <Button type="button" variant="ghost" size="icon" onClick={() => move(index, 1)} disabled={index === columns.length - 1} aria-label={`Move column ${index + 1} down`}>
                <ArrowDown className="h-4 w-4" />
              </Button>
              <Button type="button" variant="ghost" size="icon" onClick={() => onChange(columns.filter((_, i) => i !== index))} aria-label={`Remove column ${index + 1}`}>
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
            <div className={compact ? "mt-2 space-y-2" : "mt-3 grid gap-3 md:grid-cols-2"}>
              <div className="space-y-1">
                <label htmlFor={`${id}-source`} className="text-xs font-medium text-muted-foreground">Source</label>
                <SourceSelect id={`${id}-source`} value={column.source} fields={fields} onChange={(source) => patch(index, { source: source ?? "" })} />
              </div>
              <div className="space-y-1">
                <label htmlFor={`${id}-fallback`} className="text-xs font-medium text-muted-foreground">Fallback when empty</label>
                <SourceSelect id={`${id}-fallback`} value={column.fallback} fields={fields} allowNone onChange={(fallback) => patch(index, { fallback })} />
              </div>
            </div>
            {reasons?.[column.header] && (
              <p className="mt-2 text-xs text-muted-foreground">{reasons[column.header]}</p>
            )}
            <details className="group mt-2 rounded-xl bg-background px-3 py-2 shadow-[inset_0_0_0_1px_var(--input)]">
              <summary className="flex cursor-pointer list-none items-center justify-between text-xs font-medium">
                Formatting
                <span className="flex items-center gap-2">
                  {transforms.length > 0 && <Badge variant="outline">{transforms.length}</Badge>}
                  <ChevronDown className="h-4 w-4 transition-transform group-open:rotate-180" />
                </span>
              </summary>
              <div className="space-y-3 pt-3">
                <div className={compact ? "space-y-2" : "grid gap-3 md:grid-cols-2"}>
                  <div className="space-y-1">
                    <label htmlFor={`${id}-format`} className="text-xs font-medium text-muted-foreground">Number format</label>
                    <Input
                      id={`${id}-format`}
                      className="font-mono"
                      value={column.number_format ?? ""}
                      onChange={(e) => patch(index, { number_format: e.target.value || null })}
                      placeholder="e.g. #,##0.00 (blank = text)"
                    />
                  </div>
                  <div className="space-y-1">
                    <label htmlFor={`${id}-width`} className="text-xs font-medium text-muted-foreground">Column width</label>
                    <Input
                      id={`${id}-width`}
                      type="number"
                      min={4}
                      value={column.width ?? 15}
                      onChange={(e) => patch(index, { width: Math.max(4, Number.parseInt(e.target.value, 10) || 15) })}
                    />
                  </div>
                </div>
                {OUTPUT_TRANSFORMS.map((transform) => {
                  const enabled = transforms.includes(transform.value);
                  const conflicts =
                    (transform.value === "uppercase" && transforms.includes("lowercase")) ||
                    (transform.value === "lowercase" && transforms.includes("uppercase"));
                  return (
                    <label key={transform.value} className="flex items-center justify-between gap-3 text-sm">
                      <span>{transform.label}</span>
                      <Switch
                        checked={enabled}
                        disabled={conflicts || column.source.startsWith("computed.")}
                        onCheckedChange={(checked) => patch(index, {
                          transforms: checked
                            ? [...transforms, transform.value]
                            : transforms.filter((value) => value !== transform.value),
                        })}
                        aria-label={`${transform.label} for column ${column.header || index + 1}`}
                      />
                    </label>
                  );
                })}
              </div>
            </details>
          </div>
        );
      })}
      <Button type="button" variant="hairline" size="sm" onClick={() => onChange([...columns, emptyOutputColumn()])}>
        <Plus className="h-4 w-4" />
        Add column
      </Button>
    </div>
  );
}
