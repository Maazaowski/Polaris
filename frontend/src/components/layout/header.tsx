"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle, SheetClose } from "@/components/ui/sheet";
import { Menu, Search } from "lucide-react";
import { Logo } from "@/components/brand/logo";
import { useSettings } from "@/hooks/use-settings";
import { useSession } from "@/hooks/use-session";
import { NAV_SECTIONS, isCurrentPath, visibleChildren } from "./nav-config";
import { useCommandPalette } from "./command-palette";

/**
 * Header: phone widths only. On a desk the sidebar carries the logo, search
 * and navigation, so there is nothing for a top bar to do.
 */
export function Header() {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const { data: settings } = useSettings();
  const { data: session } = useSession();
  const { open: openPalette } = useCommandPalette();

  return (
    <header className="flex h-14 shrink-0 items-center gap-2 border-b border-border bg-background px-4 md:hidden">
      <Button
        variant="text"
        size="icon-sm"
        onClick={() => setMobileOpen(true)}
        aria-label="Open navigation"
      >
        <Menu className="h-4 w-4" aria-hidden="true" />
      </Button>

      <Logo variant="primary" />

      <Button
        variant="text"
        size="icon-sm"
        className="ml-auto"
        onClick={openPalette}
        aria-label="Search"
      >
        <Search className="h-4 w-4" aria-hidden="true" />
      </Button>

      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" showCloseButton>
          <div className="flex h-full flex-col">
            <div className="flex items-center border-b border-border p-4">
              <Logo variant="primary" />
              <SheetTitle className="sr-only">Polaris navigation</SheetTitle>
            </div>
            <nav className="flex-1 overflow-y-auto p-3">
              {NAV_SECTIONS.map((section) => {
                const children = visibleChildren(section, {
                  isAdmin: session?.is_admin,
                  debug: settings?.debug,
                  signedIn: !!session,
                });
                if (children.length === 0) return null;
                return (
                  <div key={section.id} className="mb-4">
                    <p className="label-mono mb-1 px-2">{section.label}</p>
                    {children.map((child) => {
                      const on = isCurrentPath(pathname, child, children);
                      return (
                        <SheetClose
                          key={child.href}
                          render={
                            <Link
                              href={child.href}
                              aria-current={on ? "page" : undefined}
                              className={cn(
                                "flex items-center gap-2.5 rounded-sm px-2 py-2 text-[14px] transition-colors",
                                on
                                  ? "bg-secondary font-semibold text-foreground"
                                  : "text-body hover:bg-secondary hover:text-foreground",
                              )}
                            >
                              <child.icon className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                              {child.label}
                            </Link>
                          }
                        />
                      );
                    })}
                  </div>
                );
              })}
            </nav>
          </div>
        </SheetContent>
      </Sheet>
    </header>
  );
}
