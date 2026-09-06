"use client";

import { useState } from "react";
import useSWR from "swr";
import { Topbar } from "@/components/layout/Topbar";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { AlertsOverTimeChart } from "@/components/charts/AlertsOverTimeChart";
import { CategoryBarChart } from "@/components/charts/CategoryBarChart";
import { SeverityBarChart } from "@/components/charts/SeverityBarChart";
import { api, fetcher } from "@/lib/api";
import type { AnalyticsData, Camera } from "@/lib/types";

const RANGES = [
  { label: "Last 7 days", days: 7 },
  { label: "Last 30 days", days: 30 },
  { label: "Last 90 days", days: 90 },
];

export default function AnalyticsPage() {
  const [rangeDays, setRangeDays] = useState(7);
  const [cameraId, setCameraId] = useState<string>("");

  const { data: camerasRes } = useSWR<{ cameras: Camera[] }>("/cameras", fetcher);
  const from = new Date(Date.now() - rangeDays * 24 * 60 * 60 * 1000).toISOString();
  const query = new URLSearchParams({ from, ...(cameraId ? { cameraId } : {}) }).toString();
  const { data } = useSWR<AnalyticsData>(`/analytics?${query}`, fetcher, { refreshInterval: 30000 });

  const cameras = camerasRes?.cameras ?? [];
  const cameraNameById = new Map(cameras.map((c) => [c.id, c.name]));

  return (
    <div>
      <Topbar title="Analytics" description="Historical trends across cameras, alerts, and incidents" />

      <div className="space-y-4 p-6">
        <div className="flex flex-wrap items-center gap-3">
          <select
            value={rangeDays}
            onChange={(e) => setRangeDays(Number(e.target.value))}
            className="rounded-md border border-surface-border bg-white/5 px-3 py-1.5 text-sm text-white outline-none"
          >
            {RANGES.map((r) => (
              <option key={r.days} value={r.days}>
                {r.label}
              </option>
            ))}
          </select>
          <select
            value={cameraId}
            onChange={(e) => setCameraId(e.target.value)}
            className="rounded-md border border-surface-border bg-white/5 px-3 py-1.5 text-sm text-white outline-none"
          >
            <option value="">All cameras</option>
            {cameras.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <p className="text-sm font-semibold text-white">Alerts Over Time</p>
            </CardHeader>
            <CardBody>
              <AlertsOverTimeChart data={data?.alertsOverTime ?? []} />
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <p className="text-sm font-semibold text-white">Incidents by Severity</p>
            </CardHeader>
            <CardBody>
              <SeverityBarChart data={data?.incidentsBySeverity ?? []} />
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <p className="text-sm font-semibold text-white">Incidents by Type</p>
            </CardHeader>
            <CardBody>
              <CategoryBarChart
                data={(data?.incidentsByType ?? []).map((d) => ({ label: d.type, count: d.count }))}
                emptyLabel="No incidents in this range yet."
              />
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <p className="text-sm font-semibold text-white">Detection Counts (by object)</p>
            </CardHeader>
            <CardBody>
              <CategoryBarChart
                data={(data?.detectionCounts ?? []).map((d) => ({ label: d.object, count: d.count }))}
                emptyLabel="No detections recorded in this range yet."
              />
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <p className="text-sm font-semibold text-white">Camera Activity</p>
            </CardHeader>
            <CardBody>
              <CategoryBarChart
                data={(data?.cameraActivity ?? []).map((d) => ({
                  label: cameraNameById.get(d.cameraId) ?? d.cameraId,
                  count: d.count,
                }))}
                emptyLabel="No camera activity recorded in this range yet."
              />
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <p className="text-sm font-semibold text-white">Review Statistics</p>
            </CardHeader>
            <CardBody>
              <CategoryBarChart
                data={(data?.reviewStats ?? []).map((d) => ({ label: d.status, count: d.count }))}
                emptyLabel="No incidents to review yet."
              />
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}
