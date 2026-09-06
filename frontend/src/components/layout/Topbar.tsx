"use client";

import useSWR from "swr";
import { LogOut } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { api } from "@/lib/api";
import type { SystemStatus } from "@/lib/types";
import clsx from "clsx";

export function Topbar({ title, description }: { title: string; description?: string }) {
  const { user, logout } = useAuth();
  const { data: status } = useSWR<SystemStatus>("/system/status", (path: string) => api.get(path), {
    refreshInterval: 15000,
  });

  return (
    <header className="flex items-center justify-between border-b border-surface-border bg-surface px-6 py-4">
      <div>
        <h1 className="text-lg font-semibold text-white">{title}</h1>
        {description && <p className="text-sm text-slate-400">{description}</p>}
      </div>

      <div className="flex items-center gap-4">
        {status && (
          <div className="flex items-center gap-3 rounded-md border border-surface-border bg-white/5 px-3 py-1.5 text-xs">
            <StatusDot ok={status.database.ok} label="DB" />
            <StatusDot ok={status.aiService.reachable} label="AI Service" />
          </div>
        )}

        <div className="flex items-center gap-3">
          <div className="text-right">
            <p className="text-sm font-medium text-white">{user?.name}</p>
            <p className="text-xs text-slate-500">{user?.role}</p>
          </div>
          <button
            onClick={logout}
            className="rounded-md p-2 text-slate-400 hover:bg-white/5 hover:text-white"
            title="Log out"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </header>
  );
}

function StatusDot({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className="flex items-center gap-1.5 text-slate-400">
      <span className={clsx("h-1.5 w-1.5 rounded-full", ok ? "bg-severity-low" : "bg-severity-critical")} />
      {label}
    </span>
  );
}
