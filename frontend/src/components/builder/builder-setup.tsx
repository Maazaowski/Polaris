"use client";

import { useRef, useState } from "react";
import { toast } from "sonner";
import { Upload, Loader2, FileText, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useProfiles } from "@/hooks/use-profiles";
import { useOutputSpecs } from "@/hooks/use-output-specs";
import { useFieldSchemas } from "@/hooks/use-field-schemas";
import { useCreateSample, type BuilderTarget } from "@/hooks/use-builder";
import { formatApiError } from "@/lib/api/errors";
import { cn } from "@/lib/utils";

const DEFAULT_FIELD_SCHEMA_ID = "invoice.standard";
const DEFAULT_OUTPUT_SPEC_ID = "temforce.standard";

export interface BuilderSetupProps {
  /** Pre-bound profile when the builder was launched from a profile page. */
  profileId: string | null;
  onReady: (sample: { id: string; name: string }, target: BuilderTarget) => void;
}

/**
 * Collect what the model is for before authoring starts: the supplier profile,
 * or — when none exists yet — the document type and deliverable directly.
 *
 * This is up front rather than at save time because it decides which columns the
 * live preview renders. Deferring it means authoring the whole model against the
 * default 8-column deliverable and only discovering the real one at the end.
 */
export function BuilderSetup({ profileId, onReady }: BuilderSetupProps) {
  const { data: profiles } = useProfiles();
  const { data: specs } = useOutputSpecs();
  const { data: schemas } = useFieldSchemas();
  const createSample = useCreateSample();
  const inputRef = useRef<HTMLInputElement>(null);

  // Launched from a profile page: the target is already decided, so only the
  // sample is missing.
  const [mode, setMode] = useState<"profile" | "direct">("profile");
  const [pickedProfile, setPickedProfile] = useState<string | null>(profileId);
  const [schemaId, setSchemaId] = useState(DEFAULT_FIELD_SCHEMA_ID);
  const [specId, setSpecId] = useState(DEFAULT_OUTPUT_SPEC_ID);
  const [sample, setSample] = useState<{ id: string; name: string } | null>(null);
  const [dragging, setDragging] = useState(false);

  const target: BuilderTarget =
    mode === "profile"
      ? { profileId: pickedProfile, outputSpecId: null, fieldSchemaId: null }
      : { profileId: null, outputSpecId: specId, fieldSchemaId: schemaId };

  const targetChosen = mode === "profile" ? !!pickedProfile : !!specId && !!schemaId;
  const canStart = targetChosen && !!sample;

  const handleFile = (file: File | undefined) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      toast.error("Please choose a PDF file");
      return;
    }
    createSample.mutate(file, {
      onSuccess: (res) => setSample({ id: res.sample_id, name: res.filename }),
      onError: (e) => toast.error(formatApiError(e)),
    });
  };

  const selectedProfileName = (profiles ?? []).find(
    (p) => p.profile_id === pickedProfile,
  )?.identity.canonical_name;

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <section className="space-y-3 rounded-3xl bg-card p-6 shadow-[inset_0_0_0_1px_var(--ring-card)]">
        <div>
          <h2 className="text-[17px] font-medium tracking-[-0.2px] text-foreground">1 · What is this template for?</h2>
          <p className="text-xs text-muted-foreground">
            Sets the document type and the deliverable columns the preview is checked against.
          </p>
        </div>

        {profileId ? (
          <p className="text-sm">
            Building for{" "}
            <span className="font-medium">{selectedProfileName ?? profileId}</span>
          </p>
        ) : (
          <>
            <Tabs value={mode} onValueChange={(v) => setMode(v as "profile" | "direct")}>
              <TabsList>
                <TabsTrigger value="profile">Existing supplier profile</TabsTrigger>
                <TabsTrigger value="direct">No profile yet</TabsTrigger>
              </TabsList>
            </Tabs>

            {mode === "profile" ? (
              <div className="space-y-1.5">
                <Label className="text-xs">Supplier profile</Label>
                <Select value={pickedProfile ?? ""} onValueChange={setPickedProfile}>
                  <SelectTrigger className="h-9 w-full">
                    {pickedProfile ? (
                      selectedProfileName ?? pickedProfile
                    ) : (
                      <span className="text-muted-foreground">Choose a profile…</span>
                    )}
                  </SelectTrigger>
                  <SelectContent>
                    {(profiles ?? []).map((p) => (
                      <SelectItem key={p.profile_id} value={p.profile_id}>
                        {p.identity.canonical_name} ({p.profile_id})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  The profile supplies the document type and expected output.
                </p>
              </div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label className="text-xs">Document type</Label>
                  <Select value={schemaId} onValueChange={(v) => v && setSchemaId(v)}>
                    <SelectTrigger className="h-9 w-full">
                      {(schemas ?? []).find((s) => s.schema_id === schemaId)?.name ?? schemaId}
                    </SelectTrigger>
                    <SelectContent>
                      {(schemas ?? []).map((s) => (
                        <SelectItem key={s.schema_id} value={s.schema_id}>
                          {s.name} ({s.schema_id})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">Which fields must be extracted.</p>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Expected output</Label>
                  <Select value={specId} onValueChange={(v) => v && setSpecId(v)}>
                    <SelectTrigger className="h-9 w-full">
                      {(specs ?? []).find((s) => s.spec_id === specId)?.name ?? specId}
                    </SelectTrigger>
                    <SelectContent>
                      {(specs ?? []).map((s) => (
                        <SelectItem key={s.spec_id} value={s.spec_id}>
                          {s.name} ({s.spec_id})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">The delivered columns.</p>
                </div>
                <p className="text-xs text-muted-foreground sm:col-span-2">
                  You can still save the template under a supplier later.
                </p>
              </div>
            )}
          </>
        )}
      </section>

      <section className="space-y-3 rounded-3xl bg-card p-6 shadow-[inset_0_0_0_1px_var(--ring-card)]">
        <div>
          <h2 className="text-[17px] font-medium tracking-[-0.2px] text-foreground">2 · Sample invoice</h2>
          <p className="text-xs text-muted-foreground">
            The PDF you author the layout rules against.
          </p>
        </div>

        <div
          className={cn(
            "flex flex-col items-center justify-center gap-3 rounded-2xl bg-background p-8 text-center transition-[box-shadow,background-color]",
            dragging ? "bg-primary-soft shadow-[inset_0_0_0_2px_var(--primary)]" : "shadow-[inset_0_0_0_1px_var(--input)]",
          )}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            handleFile(e.dataTransfer.files?.[0]);
          }}
        >
          <input
            ref={inputRef}
            type="file"
            accept="application/pdf,.pdf"
            className="hidden"
            onChange={(e) => {
              handleFile(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
          {createSample.isPending ? (
            <Loader2 className="h-7 w-7 animate-spin text-muted-foreground" />
          ) : sample ? (
            <CheckCircle2 className="h-7 w-7 text-success" />
          ) : (
            <FileText className="h-7 w-7 text-muted-foreground" />
          )}
          <div>
            <p className="text-sm font-medium">{sample ? sample.name : "Add a sample invoice PDF"}</p>
            <p className="text-xs text-muted-foreground">
              Drag &amp; drop a PDF here, or choose a file.
            </p>
          </div>
          <Button
            variant={sample ? "outline" : "default"}
            size="sm"
            onClick={() => inputRef.current?.click()}
            disabled={createSample.isPending}
          >
            <Upload className="mr-2 h-4 w-4" />
            {createSample.isPending ? "Uploading…" : sample ? "Replace PDF" : "Choose PDF"}
          </Button>
        </div>
      </section>

      <div className="flex items-center justify-end gap-3">
        {!canStart && (
          <p className="text-xs text-muted-foreground">
            {targetChosen ? "Add a sample PDF to continue." : "Choose what this model is for."}
          </p>
        )}
        <Button disabled={!canStart} onClick={() => sample && onReady(sample, target)}>
          Start building
        </Button>
      </div>
    </div>
  );
}
