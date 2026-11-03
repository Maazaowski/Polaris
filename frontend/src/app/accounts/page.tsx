"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import {
  useAccounts,
  useAssignAccounts,
  useUnassignAccounts,
  useCreateAccount,
  useSyncAccounts,
  useAccountsSyncStatus,
} from "@/hooks/use-accounts";
import { useProfiles } from "@/hooks/use-profiles";
import { safeFormatDate } from "@/lib/format-date";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Search,
  RefreshCw,
  ChevronRight,
  ChevronDown,
  Plus,
} from "lucide-react";
import type { AccountRow, AccountState } from "@/types";

const STATE_BADGE: Record<AccountState, "warning" | "success" | "destructive" | "neutral"> = {
  unmapped: "warning",
  mapped: "success",
  conflict: "destructive",
  missing: "neutral",
};

const STATE_FILTERS: (AccountState | "all")[] = ["all", "unmapped", "mapped", "conflict", "missing"];

export default function AccountsPage() {
  const { data, isLoading, isError } = useAccounts();
  const { data: profiles } = useProfiles();
  const assign = useAssignAccounts();
  const unassign = useUnassignAccounts();
  const syncMut = useSyncAccounts();
  const queryClient = useQueryClient();

  // Poll the sync status while a scan is running; reload the snapshot when it finishes.
  const [polling, setPolling] = useState(false);
  const syncStatus = useAccountsSyncStatus(polling || !!data?.syncing);
  const st = syncStatus.data;
  // Keep the local polling flag in sync with server state during render — React's
  // recommended alternative to a setState-in-effect. The two branches are mutually
  // exclusive on st.status, and each is guarded by the current value, so they
  // cannot ping-pong across re-renders.
  if (data?.syncing && st?.status !== "done" && st?.status !== "error" && !polling) {
    setPolling(true);
  } else if ((st?.status === "done" || st?.status === "error") && polling) {
    setPolling(false);
  }
  // Reload the accounts snapshot once a scan finishes.
  useEffect(() => {
    if (st?.status === "done") {
      queryClient.invalidateQueries({ queryKey: ["accounts"] });
    }
  }, [st?.status, queryClient]);
  const isSyncing =
    syncMut.isPending ||
    st?.status === "queued" ||
    st?.status === "running" ||
    (!!data?.syncing && st?.status !== "done" && st?.status !== "error");
  const syncPct = st?.customers_total
    ? Math.round((100 * (st.customers_done ?? 0)) / st.customers_total)
    : 6;

  async function doSync() {
    try {
      await syncMut.mutateAsync();
      setPolling(true);
    } catch {
      toast.error("Could not start sync.");
    }
  }

  const [search, setSearch] = useState("");
  const [stateFilter, setStateFilter] = useState<AccountState | "all">("all");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [assignTo, setAssignTo] = useState<string>("");

  const profileName = (id: string) =>
    profiles?.find((p) => p.profile_id === id)?.identity.canonical_name ?? id;

  // Filter groups/rows by search + state.
  const groups = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (data?.groups ?? [])
      .map((g) => ({
        ...g,
        accounts: g.accounts.filter((a) => {
          if (stateFilter !== "all" && a.state !== stateFilter) return false;
          if (!q) return true;
          return (
            a.account.toLowerCase().includes(q) ||
            a.customer.toLowerCase().includes(q) ||
            a.inbound_path.toLowerCase().includes(q)
          );
        }),
      }))
      .filter((g) => g.accounts.length > 0);
  }, [data, search, stateFilter]);

  const toggleGroupExpand = (customer: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(customer)) next.delete(customer);
      else next.add(customer);
      return next;
    });

  const toggleRow = (path: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });

  const toggleGroupSelect = (rows: AccountRow[]) =>
    setSelected((prev) => {
      const next = new Set(prev);
      const paths = rows.map((r) => r.inbound_path);
      const allSelected = paths.every((p) => next.has(p));
      paths.forEach((p) => (allSelected ? next.delete(p) : next.add(p)));
      return next;
    });

  const clearSelection = () => setSelected(new Set());

  async function doAssign() {
    if (!assignTo || selected.size === 0) return;
    try {
      const res = await assign.mutateAsync({
        profile_id: assignTo,
        inbound_paths: [...selected],
      });
      const detached = (res as { detached_from?: string[] })?.detached_from ?? [];
      toast.success(
        `Assigned ${selected.size} account(s) to ${profileName(assignTo)}` +
          (detached.length ? ` (detached from ${detached.length} other profile(s))` : "")
      );
      clearSelection();
    } catch {
      toast.error("Failed to assign. An account may already be mapped elsewhere.");
    }
  }

  async function doUnassign() {
    if (selected.size === 0) return;
    try {
      await unassign.mutateAsync({ inbound_paths: [...selected] });
      toast.success(`Unassigned ${selected.size} account(s). Folders left on disk.`);
      clearSelection();
    } catch {
      toast.error("Failed to unassign.");
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Accounts"
        description={
          data
            ? `${data.total_accounts} accounts under ${data.scan_base} · ${data.unmapped} unmapped, ${data.conflict} conflict, ${data.missing} missing`
            : "Discover account folders and map them to profiles."
        }
        actions={
          <>
            {data?.synced_at && !isSyncing && (
              <span className="text-[13px] text-muted-foreground">
                Scanned {safeFormatDate(data.synced_at, "d MMM HH:mm")}
              </span>
            )}
            <AddAccountDialog />
            <Button variant="hairline" onClick={doSync} disabled={isSyncing}>
              <RefreshCw className={`h-4 w-4 ${isSyncing ? "animate-spin" : ""}`} aria-hidden="true" />
              {isSyncing ? "Scanning…" : "Rescan"}
            </Button>
          </>
        }
      />

      {/* The four states, as numbers. */}
      {data && !data.never_synced && (
        <div className="fade-up fade-up-1 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[
            { label: "Mapped", value: Math.max(0, data.total_accounts - data.unmapped - data.conflict - data.missing), note: "read automatically", tone: "text-success" },
            { label: "Unmapped", value: data.unmapped, note: "no profile claims the folder", tone: "text-warning" },
            { label: "Conflicts", value: data.conflict, note: "two profiles claim the folder", tone: "text-destructive" },
            { label: "Missing folder", value: data.missing, note: "profile points at nothing", tone: "text-muted-foreground" },
          ].map((f) => (
            <div key={f.label} className="flex flex-col gap-1 rounded-3xl bg-card px-6 py-5 shadow-[inset_0_0_0_1px_var(--ring-card)]">
              <span className="text-[13px] text-muted-foreground">{f.label}</span>
              <span className="font-display text-[30px] leading-none font-medium tracking-[-0.03em] text-foreground">
                {f.value.toLocaleString()}
              </span>
              <span className={`text-[13px] font-medium ${f.tone}`}>{f.note}</span>
            </div>
          ))}
        </div>
      )}

      {/* Filters */}
      <div className="fade-up fade-up-2 flex flex-wrap items-center gap-2">
        <div role="group" aria-label="State" className="flex gap-1">
          {STATE_FILTERS.map((s) => (
            <button
              key={s}
              type="button"
              aria-pressed={stateFilter === s}
              onClick={() => setStateFilter(s)}
              className={cn(
                "h-8 rounded-full px-3.5 text-sm font-medium capitalize transition-[background-color,color,transform] duration-100 active:scale-[0.97]",
                stateFilter === s ? "bg-ink text-ink-foreground" : "text-body hover:bg-secondary hover:text-foreground",
              )}
            >
              {s}
            </button>
          ))}
        </div>
        <div className="relative ml-auto min-w-[14rem] md:max-w-xs">
          <Search className="pointer-events-none absolute top-1/2 left-3 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <Input
            placeholder="Search customer, account, folder…"
            aria-label="Search accounts"
            className="h-9 pl-9"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {/* Bulk-assign toolbar */}
      {selected.size > 0 && (
        <div className="sticky top-2 z-10 flex flex-wrap items-center gap-3 rounded-full bg-background px-5 py-2.5 shadow-[var(--shadow-overlay)]">
          <span className="text-sm font-medium">{selected.size} selected</span>
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">Assign to</span>
            <Select value={assignTo || undefined} onValueChange={(v) => setAssignTo(v ?? "")}>
              <SelectTrigger className="min-w-52">
                <SelectValue placeholder="Select a profile">
                  {(id: string | null) => (id ? profileName(id) : "Select a profile")}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {(profiles ?? []).map((p) => (
                  <SelectItem key={p.profile_id} value={p.profile_id}>
                    {p.identity.canonical_name}{" "}
                    <span className="text-muted-foreground">({p.status})</span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button onClick={doAssign} disabled={!assignTo || assign.isPending}>
              Assign
            </Button>
          </div>
          <Button variant="outline" onClick={doUnassign} disabled={unassign.isPending}>
            Unassign
          </Button>
          <Button variant="ghost" onClick={clearSelection} className="ml-auto">
            Clear
          </Button>
        </div>
      )}

      {/* Background scan progress — the disk walk runs in the worker, not here. */}
      {isSyncing && (
        <Card>
          <CardContent className="space-y-2 py-3">
            <div className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-2 text-muted-foreground">
                <RefreshCw className="h-4 w-4 animate-spin" />
                Scanning account folders…
              </span>
              <span className="text-muted-foreground">
                {st?.accounts_found ?? 0} found
                {st?.customers_total ? ` · ${st.customers_done ?? 0}/${st.customers_total} customers` : ""}
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
              <div
                className="h-full rounded-full bg-section-suppliers transition-all duration-500"
                style={{ width: `${syncPct}%` }}
              />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Content */}
      {isLoading ? (
        <LoadingState rows={6} />
      ) : isError ? (
        <ErrorState what="the accounts" />
      ) : data?.never_synced && !isSyncing ? (
        <EmptyState
          tone="green"
          title="Nothing scanned yet."
          hint="Run a scan to discover the customer and account folders on disk."
          action={
            <Button variant="solid" onClick={doSync} disabled={isSyncing}>
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              Scan now
            </Button>
          }
        />
      ) : groups.length === 0 ? (
        <EmptyState
          compact
          tone="green"
          title={
            search || stateFilter !== "all"
              ? "No accounts match the filter."
              : isSyncing
                ? "Scanning…"
                : "No account folders found under the scan directory."
          }
        />
      ) : (
        <div className="space-y-2">
          {groups.map((g) => {
            const open = expanded.has(g.customer);
            const groupPaths = g.accounts.map((a) => a.inbound_path);
            const selectedInGroup = groupPaths.filter((p) => selected.has(p)).length;
            return (
              <Card key={g.customer} className="gap-0 overflow-hidden py-0">
                <button
                  className="flex w-full items-center gap-2 px-5 py-3.5 text-left transition-colors hover:bg-background"
                  onClick={() => toggleGroupExpand(g.customer)}
                >
                  {open ? (
                    <ChevronDown className="h-4 w-4 text-muted-foreground" />
                  ) : (
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  )}
                  <span className="font-medium">{g.customer}</span>
                  <span className="text-xs text-muted-foreground">
                    {g.accounts.length} account{g.accounts.length === 1 ? "" : "s"}
                  </span>
                  {g.unmapped > 0 && (
                    <Badge variant={STATE_BADGE.unmapped}>
                      {g.unmapped} unmapped
                    </Badge>
                  )}
                  {g.conflict > 0 && (
                    <Badge variant={STATE_BADGE.conflict}>
                      {g.conflict} conflict
                    </Badge>
                  )}
                  {selectedInGroup > 0 && (
                    <span className="ml-auto text-xs text-muted-foreground">
                      {selectedInGroup} selected
                    </span>
                  )}
                </button>

                {open && (
                  <div className="border-t border-border">
                    <div className="flex items-center gap-2 border-b border-border px-5 py-2 text-xs">
                      <input
                        type="checkbox"
                        aria-label={`Select all in ${g.customer}`}
                        checked={selectedInGroup === groupPaths.length && groupPaths.length > 0}
                        onChange={() => toggleGroupSelect(g.accounts)}
                      />
                      <span className="text-muted-foreground">Select all</span>
                    </div>
                    {g.accounts.map((a) => (
                      <div
                        key={a.inbound_path}
                        className="flex items-center gap-3 border-b border-border px-5 py-2.5 text-sm transition-colors last:border-b-0 hover:bg-background data-[selected=true]:bg-primary-soft"
                        data-selected={selected.has(a.inbound_path)}
                      >
                        <input
                          type="checkbox"
                          aria-label={`Select ${a.account}`}
                          checked={selected.has(a.inbound_path)}
                          onChange={() => toggleRow(a.inbound_path)}
                        />
                        <span className="font-mono">{a.account}</span>
                        <span className="text-xs text-muted-foreground">{a.pdf_count} pdf</span>
                        <Badge variant={STATE_BADGE[a.state]}>
                          {a.state}
                        </Badge>
                        {a.profile_ids.length > 0 && (
                          <span className="text-xs text-muted-foreground">
                            {a.profile_ids.map((id, i) => (
                              <span key={id}>
                                {i > 0 && ", "}
                                <Link href={`/profiles/${id}`} className="underline hover:text-foreground">
                                  {profileName(id)}
                                </Link>
                              </span>
                            ))}
                          </span>
                        )}
                        <span className="ml-auto truncate font-mono text-xs text-muted-foreground/70">
                          {a.inbound_path}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

function AddAccountDialog() {
  const { data: profiles } = useProfiles();
  const create = useCreateAccount();
  const [open, setOpen] = useState(false);
  const [customer, setCustomer] = useState("");
  const [account, setAccount] = useState("");
  const [profileId, setProfileId] = useState("");

  async function submit() {
    if (!customer.trim() || !account.trim() || !profileId) return;
    try {
      await create.mutateAsync({ profile_id: profileId, customer: customer.trim(), account: account.trim() });
      toast.success(`Created ${customer}/${account} and mapped it.`);
      setOpen(false);
      setCustomer("");
      setAccount("");
      setProfileId("");
    } catch {
      toast.error("Failed to create the account folder.");
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button variant="outline">
            <Plus className="h-4 w-4" />
            Add account
          </Button>
        }
      />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add account</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">
            Creates <span className="font-mono">&lt;customer&gt;/&lt;account&gt;/pdf</span> and{" "}
            <span className="font-mono">/xls</span> on disk and maps it to the profile.
          </p>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Customer folder</label>
            <Input value={customer} onChange={(e) => setCustomer(e.target.value)} placeholder="e.g. 82824706" />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Account folder</label>
            <Input value={account} onChange={(e) => setAccount(e.target.value)} placeholder="e.g. A837737" />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Profile</label>
            <Select value={profileId || undefined} onValueChange={(v) => setProfileId(v ?? "")}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Select a profile">
                  {(id: string | null) =>
                    id
                      ? profiles?.find((p) => p.profile_id === id)?.identity.canonical_name ?? id
                      : "Select a profile"
                  }
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {(profiles ?? []).map((p) => (
                  <SelectItem key={p.profile_id} value={p.profile_id}>
                    {p.identity.canonical_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button onClick={submit} disabled={!customer.trim() || !account.trim() || !profileId || create.isPending}>
            Create & map
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
