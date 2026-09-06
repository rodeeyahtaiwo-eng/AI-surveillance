"use client";

import useSWR, { useSWRConfig } from "swr";
import { Camera as CameraIcon, ShieldAlert, FileWarning, Video } from "lucide-react";
import { Topbar } from "@/components/layout/Topbar";
import { StatCard } from "@/components/ui/StatCard";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { CameraFeedCard } from "@/components/monitoring/CameraFeedCard";
import { SeverityBadge, ModeBadge } from "@/components/ui/Badge";
import { AlertsOverTimeChart } from "@/components/charts/AlertsOverTimeChart";
import { api, fetcher } from "@/lib/api";
import { useRealtime } from "@/lib/useRealtime";
import { formatDateTime } from "@/lib/style";
import type { AnalyticsData, Camera, OverviewStats } from "@/lib/types";


export default function DashboardPage() {
  const { data: overview } = useSWR<OverviewStats>("/analytics/overview", fetcher, { refreshInterval: 10000 });
  const { data: camerasRes } = useSWR<{ cameras: Camera[] }>("/cameras", fetcher, { refreshInterval: 15000 });
  const from = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();
  const { data: analytics } = useSWR<AnalyticsData>(`/analytics?from=${from}`, fetcher, { refreshInterval: 30000 });
  const { mutate } = useSWRConfig();

  useRealtime((event) => {
    if (["alert.created", "incident.created", "camera.online", "camera.offline"].includes(event.type)) {
      mutate("/analytics/overview");
      mutate("/cameras");
    }
  });

  const cameras = camerasRes?.cameras ?? [];

  return (
    <div>
      <Topbar title="Dashboard" description="Overview of system status and recent activity" />

      <div className="space-y-6 p-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Total Cameras" value={overview?.totalCameras ?? "—"} icon={CameraIcon} />
          <StatCard
            label="Cameras Online"
            value={overview?.camerasOnline ?? "—"}
            icon={Video}
            tone="success"
          />
          <StatCard
            label="Active Alerts"
            value={overview?.activeAlerts ?? "—"}
            icon={ShieldAlert}
            tone={overview && overview.activeAlerts > 0 ? "danger" : "default"}
          />
          <StatCard
            label="Incidents Today"
            value={overview?.incidentsToday ?? "—"}
            icon={FileWarning}
            tone={overview && overview.incidentsToday > 0 ? "warning" : "default"}
          />
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <CardHeader>
              <p className="text-sm font-semibold text-white">Threat Activity (last 7 days)</p>
            </CardHeader>
            <CardBody>
              <AlertsOverTimeChart data={analytics?.alertsOverTime ?? []} />
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <p className="text-sm font-semibold text-white">Threat Level Summary</p>
            </CardHeader>
            <CardBody className="space-y-3">
              {(["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const).map((sev) => (
                <div key={sev} className="flex items-center justify-between">
                  <SeverityBadge severity={sev} />
                  <span className="text-sm font-semibold text-white">
                    {overview?.threatLevelSummary[sev] ?? 0}
                  </span>
                </div>
              ))}
              <p className="pt-1 text-[11px] text-slate-500">Count of active (non-reviewed) alerts by severity.</p>
            </CardBody>
          </Card>
        </div>

        <div>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-white">Live Camera Previews</h2>
            <a href="/live-monitoring" className="text-xs text-blue-400 hover:underline">
              Open Live Monitoring →
            </a>
          </div>
          {cameras.length === 0 ? (
            <Card>
              <CardBody className="text-sm text-slate-500">
                No cameras registered yet. Add one from the Cameras page.
              </CardBody>
            </Card>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {cameras.slice(0, 4).map((camera) => (
                <CameraFeedCard key={camera.id} camera={camera} variant="compact" />
              ))}
            </div>
          )}
        </div>

        <Card>
          <CardHeader className="flex items-center justify-between">
            <p className="text-sm font-semibold text-white">Recent Incidents</p>
            <a href="/incidents" className="text-xs text-blue-400 hover:underline">
              View all →
            </a>
          </CardHeader>
          <CardBody className="divide-y divide-surface-border p-0">
            {(overview?.recentIncidents.length ?? 0) === 0 ? (
              <p className="p-4 text-sm text-slate-500">No incidents recorded yet.</p>
            ) : (
              overview?.recentIncidents.map((incident) => (
                <a
                  key={incident.id}
                  href={`/incidents/${incident.id}`}
                  className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-white/5"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="truncate text-sm font-medium text-white">{incident.title}</p>
                      {incident.isDemo && <ModeBadge mode="DEMO" />}
                    </div>
                    <p className="text-xs text-slate-500">{formatDateTime(incident.createdAt)}</p>
                  </div>
                  <SeverityBadge severity={incident.severity} />
                </a>
              ))
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
