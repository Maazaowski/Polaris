"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { cn } from "@/lib/utils";
import { LogOut, Moon, Search, Sun } from "lucide-react";
import { Logo } from "@/components/brand/logo";
import { useSettings } from "@/hooks/use-settings";
import { useDashboardStats } from "@/hooks/use-dashboard";
import { useLogout, useSession } from "@/hooks/use-session";
import { useCommandPalette } from "./command-palette";
import { NAV_SECTIONS, isCurrentPath, visibleChildren } from "./nav-config";

/**
 * Sidebar: 240px, white, a hairline on the right. Every section is visible
 * under a small caps label; the current page wears the beige fill. Counts sit
 * on the right of the rows that have one.
 */
function initials(email: string): string {
  const name = email.split("@")[0] ?? "";
  const parts = name.split(/[._-]+/).filter(Boolean);
  const letters = parts.length >= 2 ? parts[0][0] + parts[1][0] : name.slice(0, 2);
  return letters.toUpperCase();
}

export function Sidebar() {
  const pathname = usePathname();
  const { data: settings } = useSettings();
  const { data: session } = useSession();
  const { data: stats } = useDashboardStats();
  const logout = useLogout();
  const { open: openPalette } = useCommandPalette();
  const { resolvedTheme, setTheme } = useTheme();

  const visibility = {
    isAdmin: session?.is_admin,
    debug: settings?.debug,
    signedIn: !!session,
  };

  const counts: Record<string, number | undefined> = {
    "/exceptions": stats?.pending_exceptions,
  };

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-sidebar-border bg-sidebar px-5 pt-7 pb-5 text-sidebar-foreground">
      <div className="mb-5 px-1">
        <Logo variant="primary" />
      </div>

      <button
        type="button"
        onClick={openPalette}
        className="mb-2 flex h-9 w-full items-center gap-2 rounded-md bg-secondary px-3 text-left text-[14px] text-muted-foreground transition-colors hover:text-foreground"
      >
        <Search className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <span className="flex-1 truncate">Search</span>
        <kbd className="font-sans text-[11px] text-muted-foreground">⌘K</kbd>
      </button>

      <nav aria-label="Primary" className="flex-1 overflow-y-auto">
        {NAV_SECTIONS.map((section) => {
          const children = visibleChildren(section, visibility);
          const primary = children.filter((c) => !c.secondary);
          const secondary = children.filter((c) => c.secondary);
          const rows = [...primary, ...secondary];
          if (rows.length === 0) return null;
          return (
            <div key={section.id} className="mt-4 first:mt-2">
              <p className="label-mono mb-1.5 px-2">{section.label}</p>
              <ul className="flex flex-col gap-0.5">
                {rows.map((child) => {
                  const on = isCurrentPath(pathname, child, children);
                  const count = counts[child.href];
                  return (
                    <li key={child.href}>
                      <Link
                        href={child.href}
                        aria-current={on ? "page" : undefined}
                        className={cn(
                          "flex h-[30px] items-center gap-2.5 rounded-sm px-2 text-[14px] tracking-[-0.09px] transition-colors duration-200",
                          on
                            ? "bg-sidebar-accent font-semibold text-sidebar-accent-foreground"
                            : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                          child.secondary && !on && "text-muted-foreground",
                        )}
                      >
                        <child.icon
                          className={cn("h-4 w-4 shrink-0", on ? "text-foreground" : "text-muted-foreground")}
                          aria-hidden="true"
                        />
                        <span className="min-w-0 flex-1 truncate">{child.label}</span>
                        {count != null && count > 0 && (
                          <span
                            className={cn(
                              "text-[12px]",
                              child.href === "/exceptions" ? "font-medium text-destructive" : "text-muted-foreground",
                            )}
                          >
                            {count}
                          </span>
                        )}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </nav>

      <div className="mt-4 flex items-center gap-2 border-t border-sidebar-border pt-4">
        {session ? (
          <>
            <Link
              href="/account"
              className="flex min-w-0 flex-1 items-center gap-2.5 rounded-sm px-1 py-1 transition-colors hover:bg-sidebar-accent"
            >
              <span
                aria-hidden="true"
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#ffcf7b] text-[11px] font-semibold text-foreground"
              >
                {initials(session.email)}
              </span>
              <span className="flex min-w-0 flex-col leading-4">
                <span className="truncate text-[14px] font-medium text-foreground">
                  {session.email.split("@")[0]}
                </span>
                <span className="truncate text-[12px] text-muted-foreground">
                  {session.is_admin ? "Admin" : "User"}
                </span>
              </span>
            </Link>
            <button
              type="button"
              onClick={() => logout.mutate()}
              disabled={logout.isPending}
              aria-label="Sign out"
              title="Sign out"
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground disabled:opacity-50"
            >
              <LogOut className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </>
        ) : (
          <span className="flex-1" />
        )}
        <button
          type="button"
          onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
          aria-label="Toggle dark mode"
          title="Toggle dark mode"
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground"
        >
          <Sun className="h-3.5 w-3.5 dark:hidden" aria-hidden="true" />
          <Moon className="hidden h-3.5 w-3.5 dark:block" aria-hidden="true" />
        </button>
      </div>
    </aside>
  );
}
