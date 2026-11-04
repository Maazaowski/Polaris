"use client";

import { useMemo } from "react";
import { Button } from "@/components/ui/button";
import { OutputColumnsEditor } from "@/components/profiles/output-columns-editor";
import { effectiveFieldSet } from "@/components/profiles/fields-editor";
import { useFieldCatalogue } from "@/hooks/use-field-catalogue";
import { useProfile } from "@/hooks/use-profiles";
import type { DraftModel } from "@/hooks/use-builder";
import type { FieldDef, OutputColumn } from "@/types";

export interface OutputEditorPanelProps {
  draft: DraftModel;
  /** The profile the template is bound to, if any. */
  profileId: string | null;
  onChange: (columns: OutputColumn[]) => void;
}

/**
 * The columns this template delivers. Bound to a profile it inherits the
 * profile's columns until the user customises them for this template; without
 * a profile it starts empty and the preview shows the raw extraction until
 * columns exist. Template columns win over the profile's when set.
 */
export function OutputEditorPanel({ draft, profileId, onChange }: OutputEditorPanelProps) {
  const { data: catalogue } = useFieldCatalogue();
  const { data: profile } = useProfile(profileId ?? "");

  // What this draft can deliver: the catalogue's always-on fields, the
  // profile's picks, and whatever the draft's own rules produce.
  const fields = useMemo<FieldDef[]>(() => {
    const base = effectiveFieldSet(profile?.fields, catalogue?.fields);
    const known = new Set(base.map((f) => `${f.scope}.${f.name}`));
    const extra: FieldDef[] = [];
    for (const name of Object.keys(draft.header_fields)) {
      if (!known.has(`document.${name}`)) {
        const cat = catalogue?.fields.find((f) => f.scope === "document" && f.name === name);
        extra.push(cat ?? { name, scope: "document", type: "string", role: "none" });
      }
    }
    for (const field of draft.item_fields) {
      if (!known.has(`row.${field.name}`)) {
        const cat = catalogue?.fields.find((f) => f.scope === "row" && f.name === field.name);
        extra.push(cat ?? { name: field.name, scope: "row", type: "string", role: "none" });
      }
    }
    return [...base, ...extra];
  }, [catalogue, profile?.fields, draft.header_fields, draft.item_fields]);

  const inherited = profile?.output_columns ?? [];
  const customised = draft.output_columns.length > 0;

  return (
    <div className="space-y-4">
      {profileId && !customised ? (
        <div className="space-y-3 rounded-2xl bg-background p-3 shadow-[inset_0_0_0_1px_var(--input)]">
          <p className="text-sm">
            Inheriting{" "}
            <span className="font-medium">{inherited.length}</span>{" "}
            column{inherited.length === 1 ? "" : "s"} from the profile.
          </p>
          {inherited.length > 0 ? (
            <p className="text-xs text-muted-foreground">{inherited.map((c) => c.header).join(", ")}</p>
          ) : (
            <p className="text-xs text-muted-foreground">
              The profile has no columns yet. Add columns here for this template, or configure them on the profile.
            </p>
          )}
          <Button
            type="button"
            variant="hairline"
            size="sm"
            onClick={() => onChange(inherited.length ? inherited.map((c) => ({ ...c })) : [])}
            disabled={inherited.length === 0}
          >
            Customise for this template
          </Button>
          {inherited.length === 0 && (
            <OutputColumnsEditor columns={draft.output_columns} fields={fields} onChange={onChange} compact />
          )}
        </div>
      ) : (
        <>
          {!profileId && !customised && (
            <p className="text-sm text-muted-foreground">
              No profile is bound, so the preview shows every field read until you add columns.
            </p>
          )}
          <OutputColumnsEditor columns={draft.output_columns} fields={fields} onChange={onChange} compact />
          {profileId && customised && (
            <Button type="button" variant="text" size="sm" onClick={() => onChange([])}>
              Back to the profile&apos;s columns
            </Button>
          )}
        </>
      )}
      <p className="text-xs text-muted-foreground">
        Template columns win over the profile&apos;s when set; leave them empty to deliver what the profile configures.
      </p>
    </div>
  );
}
