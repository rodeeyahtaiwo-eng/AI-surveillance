"use client";

import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { EmptyState } from "./AlertsOverTimeChart";

// Fixed categorical order (never cycled/reused) — see tailwind.config.ts "chart".
const SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"];

/** Single-measure categorical bar chart (e.g. detections by object, activity by camera). */
export function CategoryBarChart({
  data,
  emptyLabel = "No data yet.",
}: {
  data: { label: string; count: number }[];
  emptyLabel?: string;
}) {
  if (data.length === 0) return <EmptyState label={emptyLabel} />;

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
        <CartesianGrid stroke="#2c2c2a" horizontal={false} />
        <XAxis type="number" stroke="#898781" fontSize={11} tickLine={false} axisLine={{ stroke: "#383835" }} allowDecimals={false} />
        <YAxis
          type="category"
          dataKey="label"
          stroke="#c3c2b7"
          fontSize={12}
          tickLine={false}
          axisLine={false}
          width={110}
        />
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
        <Bar dataKey="count" radius={[0, 4, 4, 0]} maxBarSize={18}>
          {data.map((entry, i) => (
            <Cell key={entry.label} fill={SERIES[i % SERIES.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
