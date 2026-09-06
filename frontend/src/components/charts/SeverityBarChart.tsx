"use client";

import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { EmptyState } from "./AlertsOverTimeChart";
import type { Severity } from "@/lib/types";

// Fixed status palette (good/warning/serious/critical) — each bar IS that severity, so
// reusing status color here is the correct case, not series-identity color abuse.
const SEVERITY_COLOR: Record<string, string> = {
  LOW: "#0ca30c",
  MEDIUM: "#fab219",
  HIGH: "#ec835a",
  CRITICAL: "#d03b3b",
};
const ORDER: Severity[] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];

export function SeverityBarChart({ data }: { data: { severity: string; count: number }[] }) {
  const bySeverity = new Map(data.map((d) => [d.severity, d.count]));
  const ordered = ORDER.map((s) => ({ severity: s, count: bySeverity.get(s) ?? 0 }));

  if (data.length === 0) return <EmptyState label="No incidents in this range yet." />;

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={ordered} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
        <CartesianGrid stroke="#2c2c2a" vertical={false} />
        <XAxis dataKey="severity" stroke="#c3c2b7" fontSize={11} tickLine={false} axisLine={{ stroke: "#383835" }} />
        <YAxis stroke="#898781" fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} width={28} />
        <Tooltip
          cursor={{ fill: "rgba(255,255,255,0.04)" }}
          contentStyle={{
            background: "#111826",
            border: "1px solid #1f2937",
            borderRadius: 8,
            fontSize: 12,
            color: "#e2e8f0",
          }}
        />
        <Bar dataKey="count" radius={[4, 4, 0, 0]} maxBarSize={40}>
          {ordered.map((entry) => (
            <Cell key={entry.severity} fill={SEVERITY_COLOR[entry.severity]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
