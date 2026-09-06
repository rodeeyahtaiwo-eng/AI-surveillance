"use client";

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

/**
 * Single-series magnitude-over-time chart — sequential blue hue per the dataviz skill
 * (single series needs no legend; the chart title/axis already names it).
 */
export function AlertsOverTimeChart({ data }: { data: { date: string; count: number }[] }) {
  if (data.length === 0) {
    return <EmptyState label="No alerts recorded in this range yet." />;
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={data} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
        <defs>
          <linearGradient id="alertsFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3987e5" stopOpacity={0.35} />
            <stop offset="100%" stopColor="#3987e5" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="#2c2c2a" vertical={false} />
        <XAxis dataKey="date" stroke="#898781" fontSize={11} tickLine={false} axisLine={{ stroke: "#383835" }} />
        <YAxis stroke="#898781" fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} width={28} />
        <Tooltip
          contentStyle={{
            background: "#111826",
            border: "1px solid #1f2937",
            borderRadius: 8,
            fontSize: 12,
            color: "#e2e8f0",
          }}
          labelStyle={{ color: "#c3c2b7" }}
        />
        <Area
          type="monotone"
          dataKey="count"
          name="Alerts"
          stroke="#3987e5"
          strokeWidth={2}
          fill="url(#alertsFill)"
          dot={false}
          activeDot={{ r: 4 }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function EmptyState({ label }: { label: string }) {
  return (
    <div className="flex h-[220px] items-center justify-center text-sm text-slate-500">{label}</div>
  );
}
