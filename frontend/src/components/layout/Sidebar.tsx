"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import {
  LayoutDashboard,
  Video,
  Camera,
  Bell,
  FileWarning,
  BarChart3,
  Users,
  Settings,
  ShieldAlert,
} from "lucide-react";

interface NavItem {
  href: string;
  label: string;
  icon: typeof Video;
  /** Live Monitoring is the primary landing page (see docs/architecture.md) — visually
   * called out rather than treated as just another list item. */
  primary?: boolean;
}

interface NavSection {
  label: string;
  items: NavItem[];
}

const sections: NavSection[] = [
  {
    label: "Monitoring",
    items: [
      { href: "/live-monitoring", label: "Live Monitoring", icon: Video, primary: true },
      { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
      { href: "/cameras", label: "Cameras", icon: Camera },
    ],
  },
  {
    label: "Security",
    items: [
      { href: "/alerts", label: "Alerts", icon: Bell },
      { href: "/incidents", label: "Incidents", icon: FileWarning },
    ],
  },
  {
    label: "Analytics",
    items: [{ href: "/analytics", label: "Analytics", icon: BarChart3 }],
  },
  {
    label: "Administration",
    items: [
      { href: "/users", label: "Users", icon: Users },
      { href: "/settings", label: "Settings", icon: Settings },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-screen w-60 shrink-0 flex-col border-r border-surface-border bg-surface-raised">
      <div className="flex items-center gap-2 border-b border-surface-border px-4 py-4">
        <ShieldAlert className="h-6 w-6 text-blue-400" />
        <div>
          <p className="text-sm font-semibold text-white leading-none">AI Surveillance</p>
          <p className="text-[11px] text-slate-500">Threat Detection SOC</p>
        </div>
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto p-2 pt-3">
        {sections.map((section) => (
          <div key={section.label}>
            <p className="px-3 pb-1 text-[10px] font-bold uppercase tracking-widest text-slate-600">
              {section.label}
            </p>
            <div className="space-y-1">
              {section.items.map((item) => {
                const active = pathname === item.href || pathname?.startsWith(item.href + "/");
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={clsx(
                      "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                      active
                        ? "bg-blue-500/10 text-blue-300"
                        : item.primary
                        ? "text-slate-200 hover:bg-white/5"
                        : "text-slate-400 hover:bg-white/5 hover:text-slate-200"
                    )}
                  >
                    <Icon className={clsx("h-4 w-4", item.primary && !active && "text-blue-400")} />
                    {item.label}
                    {item.primary && (
                      <span
                        className={clsx(
                          "ml-auto h-1.5 w-1.5 rounded-full",
                          active ? "bg-blue-400" : "bg-blue-500/50"
                        )}
                      />
                    )}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>
    </aside>
  );
}
