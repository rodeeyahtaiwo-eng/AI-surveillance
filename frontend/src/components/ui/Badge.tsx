import clsx from "clsx";
import type { Severity } from "@/lib/types";
import { severityStyles } from "@/lib/style";

export function SeverityBadge({ severity }: { severity: Severity }) {
  const s = severityStyles[severity];
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-semibold tracking-wide",
        s.bg,
        s.text
      )}
    >
      <span className={clsx("h-1.5 w-1.5 rounded-full", s.dot)} />
      {severity}
    </span>
  );
}

export function DemoBadge() {
  return (
    <span
      title="Simulated data — see docs/demo.md. Never a real security event."
      className="inline-flex items-center rounded-md border border-violet-500/30 bg-violet-500/10 px-2 py-0.5 text-[10px] font-bold tracking-widest text-violet-300"
    >
      DEMO
    </span>
  );
}

export function ModeBadge({ mode }: { mode: "REAL" | "DEMO" }) {
  if (mode === "DEMO") return <DemoBadge />;
  return (
    <span className="inline-flex items-center rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-bold tracking-widest text-emerald-300">
      REAL
    </span>
  );
}

export function Pill({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-md border border-surface-border bg-white/5 px-2 py-0.5 text-xs text-slate-300",
        className
      )}
    >
      {children}
    </span>
  );
}
