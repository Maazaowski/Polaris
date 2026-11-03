"use client";

import { usePathname } from "next/navigation";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import { CommandPaletteProvider } from "@/components/layout/command-palette";

/** App chrome (sidebar on a desk, a slim bar on a phone) for every page except bare /login. */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  if (pathname === "/login") {
    return <main className="h-full">{children}</main>;
  }

  return (
    <CommandPaletteProvider>
      <div className="flex h-full">
        <div className="hidden md:flex">
          <Sidebar />
        </div>
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <Header />
          <main className="flex-1 overflow-auto px-4 py-5 md:px-12 md:py-10">
            <div className="mx-auto w-full max-w-[1320px]">{children}</div>
          </main>
        </div>
      </div>
    </CommandPaletteProvider>
  );
}
