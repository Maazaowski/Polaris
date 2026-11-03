import {
  AlertTriangle,
  Boxes,
  Bug,
  Database,
  FileText,
  FlaskConical,
  Gauge,
  Landmark,
  LayoutGrid,
  ScrollText,
  Settings,
  Table,
  Upload,
  UserCircle2,
  UserCog,
  Users,
  type LucideIcon,
} from "lucide-react";

/**
 * Navigation: four sections, each with a handful of pages, all visible at once
 * in the sidebar under a small caps label.
 *
 *   Work       the operator's daily screens
 *   Suppliers  how each supplier's invoices are recognised, read and delivered
 *   Templates  the reusable extraction models and the visual builder
 *   System     insights, settings, people
 *
 * Routes are unchanged; this is information architecture, not routing.
 */

export type NavChild = {
  href: string;
  label: string;
  /** Shown in the command palette. */
  hint?: string;
  icon: LucideIcon;
  adminOnly?: boolean;
  debugOnly?: boolean;
  sessionOnly?: boolean;
  /** Secondary pages: reachable from the sidebar's "more" group and the palette. */
  secondary?: boolean;
};

export type NavSection = {
  id: "work" | "suppliers" | "templates" | "system";
  href: string;
  label: string;
  icon: LucideIcon;
  /** Any route under these prefixes lights this section up. */
  match: string[];
  children: NavChild[];
};

export const NAV_SECTIONS: NavSection[] = [
  {
    id: "work",
    href: "/invoices",
    label: "Work",
    icon: FileText,
    match: ["/invoices", "/exceptions", "/upload", "/"],
    children: [
      { href: "/invoices", label: "Queue", hint: "Everything that came in", icon: FileText },
      { href: "/exceptions", label: "Needs you", hint: "Failed and variance", icon: AlertTriangle },
      { href: "/upload", label: "Upload", hint: "Add invoices by hand", icon: Upload },
    ],
  },
  {
    id: "suppliers",
    href: "/profiles",
    label: "Suppliers",
    icon: Users,
    match: ["/profiles", "/accounts", "/field-schemas", "/output-specs"],
    children: [
      { href: "/profiles", label: "Suppliers", hint: "One profile per supplier", icon: Users },
      { href: "/accounts", label: "Accounts", hint: "Customer folders on disk", icon: Landmark },
      { href: "/field-schemas", label: "Field schemas", hint: "What we extract", icon: Database, secondary: true },
      { href: "/output-specs", label: "Deliverables", hint: "What we deliver", icon: Table, secondary: true },
    ],
  },
  {
    id: "templates",
    href: "/models",
    label: "Templates",
    icon: Boxes,
    match: ["/models"],
    children: [
      { href: "/models", label: "Templates", hint: "Written once, run for free", icon: Boxes },
      { href: "/models/builder", label: "Builder", hint: "Draw a template by hand", icon: LayoutGrid },
    ],
  },
  {
    id: "system",
    href: "/insights",
    label: "System",
    icon: Settings,
    match: ["/settings", "/insights", "/logs", "/users", "/account", "/ai-calls", "/evals"],
    children: [
      { href: "/insights", label: "Insights", hint: "Cost and volume over time", icon: Gauge },
      { href: "/settings", label: "Settings", hint: "Provider, thresholds, watcher", icon: Settings },
      { href: "/logs", label: "Audit and usage", hint: "Processing trail and AI spend", icon: ScrollText, secondary: true },
      { href: "/users", label: "People", hint: "Accounts and roles", icon: UserCog, adminOnly: true, secondary: true },
      { href: "/account", label: "My account", hint: "Password and session", icon: UserCircle2, sessionOnly: true, secondary: true },
      { href: "/ai-calls", label: "AI calls", hint: "Captured prompts", icon: Bug, debugOnly: true, secondary: true },
      { href: "/evals", label: "Evals", hint: "Labelled regression corpus", icon: FlaskConical, debugOnly: true, secondary: true },
    ],
  },
];

/** Reserved for commands that are not also nav destinations. */
export const EXTRA_COMMANDS: NavChild[] = [];

export function sectionForPath(pathname: string): NavSection | undefined {
  return NAV_SECTIONS.find((s) =>
    s.match.some((m) =>
      m === "/" ? pathname === "/" : pathname === m || pathname.startsWith(m + "/"),
    ),
  );
}

export function visibleChildren(
  section: NavSection,
  { isAdmin, debug, signedIn }: { isAdmin?: boolean; debug?: boolean; signedIn?: boolean },
): NavChild[] {
  return section.children.filter((c) => {
    if (c.adminOnly && !isAdmin) return false;
    if (c.debugOnly && !debug) return false;
    if (c.sessionOnly && !signedIn) return false;
    return true;
  });
}

/** Is this child the current page? `/models` must not light up for `/models/builder`. */
export function isCurrentPath(pathname: string, child: NavChild, siblings: NavChild[]): boolean {
  if (pathname === child.href) return true;
  if (!pathname.startsWith(child.href + "/")) return false;
  // A more specific sibling owns this path.
  return !siblings.some(
    (s) => s !== child && s.href.length > child.href.length && pathname.startsWith(s.href),
  );
}
