"use client";

import { useMemo, useState } from "react";
import { Plus, Trash2, X } from "lucide-react";
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
import { Switch } from "@/components/ui/switch";
import { TagInput } from "@/components/form/tag-input";
import { useFieldCatalogue } from "@/hooks/use-field-catalogue";
import type { CatalogueField, FieldDef } from "@/types";

export const FIELD_TYPES = ["string", "date", "number", "currency", "integer", "enum"];
export const FIELD_ROLES = [
  "none", "identifier", "amount", "tax", "subtotal", "total", "tax_rate", "excluded_total",
];

const DATE_FORMAT_SUGGESTIONS = [
  "%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d", "%m-%d-%Y", "%d-%m-%Y", "%d.%m.%Y", "%d %B %Y", "%B %Y",
];

const ACRONYMS: Record<string, string> = { id: "ID", po: "PO", ban: "BAN", vat: "VAT" };

export function humanizeFieldName(name: string): string {
  return name
    .split("_")
    .map((w) => ACRONYMS[w] ?? w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export function fieldKey(field: Pick<FieldDef, "scope" | "name">): string {
  return `${field.scope}.${field.name}`;
}

/** The fields a profile reads: the catalogue's always-on fields merged with the
 * profile's own picks (profile entry wins). Mirrors `profiles/contract.field_set`
 * so the editor offers exactly the sources the backend will resolve. */
export function effectiveFieldSet(
  picks: FieldDef[] | undefined,
  catalogue: CatalogueField[] | undefined,
): FieldDef[] {
  const byKey = new Map<string, FieldDef>();
  for (const f of catalogue ?? []) {
    if (f.always_on) byKey.set(fieldKey(f), { ...f });
  }
  for (const pick of picks ?? []) {
    const base = (catalogue ?? []).find((f) => f.scope === pick.scope && f.name === pick.name);
    byKey.set(fieldKey(pick), base
      ? { ...base, ...pick, type: base.type, role: base.role, enum_values: base.enum_values }
      : { ...pick });
  }
  return Array.from(byKey.values());
}

function emptyCustomField(): FieldDef {
  return {
    name: "",
    scope: "row",
    type: "string",
    role: "none",
    label_hint: null,
    date_format: null,
    required: false,
    enum_values: [],
    description: "",
  };
}

export interface FieldsEditorProps {
  fields: FieldDef[];
  onChange: (fields: FieldDef[]) => void;
  /** Compact layout for narrow panels (the builder sidebar). */
  compact?: boolean;
}

/**
 * What this supplier's invoices are read for. Starts empty; the user picks from
 * the catalogue (type and role are the catalogue's) or adds a custom field.
 * Each pick carries the supplier's printed label, date format and required flag.
 */
export function FieldsEditor({ fields, onChange, compact = false }: FieldsEditorProps) {
  const { data: catalogue } = useFieldCatalogue();
  const [pickerOpen, setPickerOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [customOpen, setCustomOpen] = useState(false);
  const [custom, setCustom] = useState<FieldDef>(emptyCustomField());

  const selectedKeys = useMemo(() => new Set(fields.map(fieldKey)), [fields]);
  const catalogueByKey = useMemo(
    () => new Map((catalogue?.fields ?? []).map((f) => [fieldKey(f), f])),
    [catalogue],
  );
  const alwaysOn = (catalogue?.fields ?? []).filter((f) => f.always_on);

  const candidates = (catalogue?.fields ?? []).filter((f) => {
    if (selectedKeys.has(fieldKey(f))) return false;
    const q = query.trim().toLowerCase();
    if (!q) return true;
    return (
      f.name.includes(q) ||
      humanizeFieldName(f.name).toLowerCase().includes(q) ||
      (f.description ?? "").toLowerCase().includes(q)
    );
  });

  function addPick(f: CatalogueField) {
    onChange([
      ...fields,
      {
        name: f.name,
        scope: f.scope,
        type: f.type,
        role: f.role,
        label_hint: null,
        date_format: null,
        required: false,
      },
    ]);
    setQuery("");
  }

  function addCustom() {
    const name = custom.name.trim();
    if (!/^[a-z][a-z0-9_]*$/.test(name)) return;
    if (selectedKeys.has(`${custom.scope}.${name}`)) return;
    onChange([...fields, { ...custom, name, description: custom.description ?? "" }]);
    setCustom(emptyCustomField());
    setCustomOpen(false);
  }

  function patch(field: FieldDef, update: Partial<FieldDef>) {
    onChange(fields.map((f) => (fieldKey(f) === fieldKey(field) ? { ...f, ...update } : f)));
  }

  function remove(field: FieldDef) {
    onChange(fields.filter((f) => fieldKey(f) !== fieldKey(field)));
  }

  const groups: Array<{ scope: "document" | "row"; title: string }> = [
    { scope: "document", title: "Document fields" },
    { scope: "row", title: "Line-item fields" },
  ];
  const customNameValid = /^[a-z][a-z0-9_]*$/.test(custom.name.trim());

  return (
    <div className="space-y-4">
      {fields.length === 0 && (
        <p className="text-sm text-muted-foreground">
          Nothing is read yet. Add the fields this supplier&apos;s invoices should be read for.
        </p>
      )}

      {groups.map(({ scope, title }) => {
        const group = fields.filter((f) => f.scope === scope);
        if (group.length === 0) return null;
        return (
          <div key={scope} className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{title}</p>
            {group.map((field) => {
              const base = catalogueByKey.get(fieldKey(field));
              const isCustom = !base;
              return (
                <div
                  key={fieldKey(field)}
                  className="rounded-2xl p-3 shadow-[inset_0_0_0_1px_var(--input)]"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium">{humanizeFieldName(field.name)}</span>
                    <Badge variant="outline">{field.type}</Badge>
                    {field.role && field.role !== "none" && <Badge variant="outline">{field.role}</Badge>}
                    {isCustom && <Badge variant="secondary">Custom</Badge>}
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="ml-auto"
                      onClick={() => remove(field)}
                      aria-label={`Remove field ${field.name}`}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                  {base?.description && !compact && (
                    <p className="mt-1 text-xs text-muted-foreground">{base.description}</p>
                  )}
                  <div className={compact ? "mt-2 space-y-2" : "mt-3 grid gap-3 md:grid-cols-2"}>
                    <div className="space-y-1">
                      <label htmlFor={`label-${fieldKey(field)}`} className="text-xs font-medium text-muted-foreground">
                        Printed label
                      </label>
                      <Input
                        id={`label-${fieldKey(field)}`}
                        value={field.label_hint ?? ""}
                        onChange={(e) => patch(field, { label_hint: e.target.value || null })}
                        placeholder={base?.label_hint ? `Default: ${base.label_hint}` : "What this supplier calls it"}
                      />
                    </div>
                    {field.type === "date" && (
                      <div className="space-y-1">
                        <label htmlFor={`date-${fieldKey(field)}`} className="text-xs font-medium text-muted-foreground">
                          Printed date format
                        </label>
                        <Input
                          id={`date-${fieldKey(field)}`}
                          list={`date-formats-${fieldKey(field)}`}
                          className="font-mono"
                          value={field.date_format ?? ""}
                          onChange={(e) => patch(field, { date_format: e.target.value || null })}
                          placeholder="e.g. %d/%m/%Y"
                          autoComplete="off"
                        />
                        <datalist id={`date-formats-${fieldKey(field)}`}>
                          {DATE_FORMAT_SUGGESTIONS.map((v) => (
                            <option key={v} value={v} />
                          ))}
                        </datalist>
                      </div>
                    )}
                    {field.type === "enum" && isCustom && (
                      <div className="space-y-1 md:col-span-2">
                        <span className="text-xs font-medium text-muted-foreground">Allowed values</span>
                        <TagInput
                          value={field.enum_values ?? []}
                          onChange={(enum_values) => patch(field, { enum_values })}
                          placeholder="Add value"
                        />
                      </div>
                    )}
                    <label className="flex items-center justify-between gap-3 rounded-xl px-3 py-2 text-sm shadow-[inset_0_0_0_1px_var(--input)]">
                      <span>Required</span>
                      <Switch
                        checked={Boolean(field.required)}
                        onCheckedChange={(required) => patch(field, { required })}
                        aria-label={`Field ${field.name} is required`}
                      />
                    </label>
                  </div>
                </div>
              );
            })}
          </div>
        );
      })}

      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="hairline"
          size="sm"
          onClick={() => {
            setPickerOpen((v) => !v);
            setCustomOpen(false);
          }}
        >
          <Plus className="h-4 w-4" />
          Add field
        </Button>
        <Button
          type="button"
          variant="text"
          size="sm"
          onClick={() => {
            setCustomOpen((v) => !v);
            setPickerOpen(false);
          }}
        >
          Custom field
        </Button>
      </div>

      {pickerOpen && (
        <div className="space-y-2 rounded-2xl bg-background p-3 shadow-[inset_0_0_0_1px_var(--input)]">
          <div className="flex items-center gap-2">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search the catalogue"
              aria-label="Search the field catalogue"
              autoFocus
            />
            <Button type="button" variant="ghost" size="icon" onClick={() => setPickerOpen(false)} aria-label="Close field picker">
              <X className="h-4 w-4" />
            </Button>
          </div>
          <div className="max-h-64 space-y-1 overflow-y-auto">
            {candidates.length === 0 && (
              <p className="px-1 py-2 text-xs text-muted-foreground">
                {catalogue ? "No matching catalogue field. Add it as a custom field." : "Loading the catalogue…"}
              </p>
            )}
            {candidates.map((f) => (
              <button
                key={fieldKey(f)}
                type="button"
                onClick={() => addPick(f)}
                className="flex w-full items-start gap-2 rounded-xl px-2 py-1.5 text-left text-sm hover:bg-card"
              >
                <span className="font-medium">{humanizeFieldName(f.name)}</span>
                <span className="text-xs text-muted-foreground">
                  {f.scope} · {f.type}
                  {f.role !== "none" ? ` · ${f.role}` : ""}
                  {f.always_on ? " · always read" : ""}
                </span>
                {f.description && !compact && (
                  <span className="ml-auto max-w-[45%] truncate text-xs text-muted-foreground">{f.description}</span>
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      {customOpen && (
        <div className="grid gap-3 rounded-2xl bg-background p-3 shadow-[inset_0_0_0_1px_var(--input)] md:grid-cols-2">
          <div className="space-y-1">
            <label htmlFor="custom-field-name" className="text-xs font-medium text-muted-foreground">Name</label>
            <Input
              id="custom-field-name"
              className="font-mono"
              value={custom.name}
              onChange={(e) => setCustom({ ...custom, name: e.target.value.toLowerCase() })}
              placeholder="site_code"
            />
            <p className="text-[11px] text-muted-foreground">Lowercase letters, digits and underscores.</p>
          </div>
          <div className="space-y-1">
            <label htmlFor="custom-field-scope" className="text-xs font-medium text-muted-foreground">Scope</label>
            <Select value={custom.scope} onValueChange={(scope) => setCustom({ ...custom, scope: (scope as "document" | "row") ?? "row" })}>
              <SelectTrigger id="custom-field-scope" className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="document">Document (once per invoice)</SelectItem>
                <SelectItem value="row">Row (once per line item)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <label htmlFor="custom-field-type" className="text-xs font-medium text-muted-foreground">Type</label>
            <Select value={custom.type} onValueChange={(type) => setCustom({ ...custom, type: type ?? "string" })}>
              <SelectTrigger id="custom-field-type" className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                {FIELD_TYPES.map((t) => <SelectItem key={t} value={t}>{humanizeFieldName(t)}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <label htmlFor="custom-field-role" className="text-xs font-medium text-muted-foreground">Role</label>
            <Select value={custom.role} onValueChange={(role) => setCustom({ ...custom, role: role ?? "none" })}>
              <SelectTrigger id="custom-field-role" className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                {FIELD_ROLES.map((r) => <SelectItem key={r} value={r}>{humanizeFieldName(r)}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1 md:col-span-2">
            <label htmlFor="custom-field-description" className="text-xs font-medium text-muted-foreground">Description</label>
            <Input
              id="custom-field-description"
              value={custom.description ?? ""}
              onChange={(e) => setCustom({ ...custom, description: e.target.value })}
              placeholder="What the extractor should look for"
            />
          </div>
          {custom.type === "enum" && (
            <div className="space-y-1 md:col-span-2">
              <span className="text-xs font-medium text-muted-foreground">Allowed values</span>
              <TagInput
                value={custom.enum_values ?? []}
                onChange={(enum_values) => setCustom({ ...custom, enum_values })}
                placeholder="Add value"
              />
            </div>
          )}
          <div className="flex justify-end gap-2 md:col-span-2">
            <Button type="button" variant="text" size="sm" onClick={() => setCustomOpen(false)}>Cancel</Button>
            <Button type="button" size="sm" onClick={addCustom} disabled={!customNameValid}>
              Add custom field
            </Button>
          </div>
        </div>
      )}

      {alwaysOn.length > 0 && !compact && (
        <p className="text-[11px] text-muted-foreground">
          Always read, whether or not listed:{" "}
          {Array.from(new Set(alwaysOn.map((f) => f.name))).map(humanizeFieldName).join(", ")}.
        </p>
      )}
    </div>
  );
}
