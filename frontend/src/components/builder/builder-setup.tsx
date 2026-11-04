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
import { useCreateSample, type BuilderTarget } from "@/hooks/use-builder";
import { formatApiError } from "@/lib/api/errors";
import { cn } from "@/lib/utils";

export interface BuilderSetupProps {
  /** Pre-bound profile when the builder was launched from a profile page. */
  profileId: string | null;
  onReady: (sample: { id: string; name: string }, target: BuilderTarget) => void;
}

/**
 * Collect what the model is for before authoring starts: the supplier profile
 * whose columns the live preview renders, or no profile yet (the template then
 * carries its own columns from the Output tab, and the preview shows the raw
 * extraction until it has some).
 */
export function BuilderSetup({ profileId, onReady }: BuilderSetupProps) {
  const { data: profiles } = useProfiles();
  const createSample = useCreateSample();
  const inputRef = useRef<HTMLInputElement>(null);

  const [mode, setMode] = useState<"profile" | "direct">("profile");
  const [pickedProfile, setPickedProfile] = useState<string | null>(profileId);
  const [sample, setSample] = useState<{ id: string; name: string } | null>(null);
  const [dragging, setDragging] = useState(false);

  const target: BuilderTarget = { profileId: mode === "profile" ? pickedProfile : null };
  const targetChosen = mode === "direct" || !!pickedProfile;
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

  const selectedProfile = (profiles ?? []).find((p) => p.profile_id === pickedProfile);
  const selectedProfileName = selectedProfile?.identity.canonical_name;

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <section className="space-y-3 rounded-3xl bg-card p-6 shadow-[inset_0_0_0_1px_var(--ring-card)]">
        <div>
          <h2 className="text-[17px] font-medium tracking-[-0.2px] text-foreground">1 · What is this template for?</h2>
          <p className="text-xs text-muted-foreground">
            A supplier profile supplies the fields to read and the columns the preview is checked against.
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
                  <SelectTrigger className="h-9 w-full" aria-label="Supplier profile">
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
                  {selectedProfile
                    ? `${selectedProfile.output_columns.length} delivered column${selectedProfile.output_columns.length === 1 ? "" : "s"} configured on the profile.`
                    : "The profile supplies the document type and the delivered columns."}
                </p>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">
                The preview will show every field the template reads until you add delivered columns on the
                Output tab. You can still save the template under a supplier later.
              </p>
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
