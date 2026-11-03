"use client";

import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { sectionForPath } from "@/components/layout/nav-config";

interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  /**
   * The coloured one-word label above the title. Defaults to the section the
   * route belongs to (Work, Suppliers, Templates, System); pass `null` to omit.
   */
  eyebrow?: string | null;
  /** Rendered beside the title: an avatar disc, a status pill. */
  leading?: React.ReactNode;
  /** The title is an id or filename; set it in mono. */
  mono?: boolean;
  className?: string;
}

const SECTION_TONE: Record<string, string> = {
  work: "text-section-work",
  suppliers: "text-section-suppliers",
  templates: "text-section-templates",
  system: "text-section-system",
};

export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
  leading,
  mono,
  className,
}: PageHeaderProps) {
  const pathname = usePathname();
  const section = sectionForPath(pathname);
  const label = eyebrow === undefined ? section?.label : eyebrow;
  const tone = section ? SECTION_TONE[section.id] : "text-muted-foreground";

  return (
    <div className={cn("fade-up flex flex-wrap items-end justify-between gap-4", className)}>
      <div className="flex min-w-0 items-center gap-4">
        {leading}
        <div className="flex min-w-0 flex-col gap-1">
          {label && <span className={cn("eyebrow", tone)}>{label}</span>}
          {/* The page's single <h1>. */}
          <h1
            className={cn(
              "text-[32px] leading-[1.15] font-semibold tracking-[-0.45px] text-foreground",
              mono && "font-mono text-[26px] font-medium tracking-normal",
            )}
          >
            {title}
          </h1>
          {description && <p className="text-[15px] text-muted-foreground">{description}</p>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
