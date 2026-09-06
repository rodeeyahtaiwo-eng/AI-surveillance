"use client";

import useSWR from "swr";
import { Topbar } from "@/components/layout/Topbar";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { api, fetcher } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

interface Settings {
  threatThresholds: Record<string, number>;
  notificationProvider: string;
  aiServiceUrl: string;
}


export default function SettingsPage() {
  const { user } = useAuth();
  const { data } = useSWR<Settings>("/system/settings", fetcher);

  return (
    <div>
      <Topbar title="Settings" description="System configuration (read-only for this build)" />

      <div className="space-y-4 p-6">
        <Card>
          <CardHeader>
            <p className="text-sm font-semibold text-white">Administrator Profile</p>
          </CardHeader>
          <CardBody className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Name</p>
              <p className="text-slate-300">{user?.name}</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Email</p>
              <p className="text-slate-300">{user?.email}</p>
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <p className="text-sm font-semibold text-white">Threat / Alert Thresholds</p>
          </CardHeader>
          <CardBody>
            <p className="mb-3 text-xs text-slate-500">
              The 0.0–1.0 threat score computed by the AI service is mapped to a severity by these
              thresholds — owned by the backend (
              <code className="rounded bg-white/10 px-1 py-0.5">backend/src/config/threatConfig.ts</code>),
              not the frontend. Editable-from-UI thresholds are a natural next step (would move this into
              the database) but are intentionally not exposed as freeform config from the browser yet, per
              the project's "no unsafe model configuration from the frontend" rule.
            </p>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {data &&
                Object.entries(data.threatThresholds).map(([level, value]) => (
                  <div key={level} className="rounded-md border border-surface-border bg-white/5 px-3 py-2">
                    <p className="text-xs text-slate-500">{level}</p>
                    <p className="text-lg font-semibold text-white">{value.toFixed(2)}</p>
                  </div>
                ))}
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <p className="text-sm font-semibold text-white">Notifications</p>
          </CardHeader>
          <CardBody className="text-sm text-slate-300">
            Active provider: <span className="text-white">{data?.notificationProvider ?? "—"}</span>
            <p className="mt-1 text-xs text-slate-500">
              Real email/SMS/push providers are configured via backend environment variables — see
              docs/setup.md. Credentials are never stored in or sent to the frontend.
            </p>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <p className="text-sm font-semibold text-white">AI Service</p>
          </CardHeader>
          <CardBody className="text-sm text-slate-300">
            Endpoint: <span className="font-mono text-xs text-white">{data?.aiServiceUrl ?? "—"}</span>
            <p className="mt-1 text-xs text-slate-500">
              See docs/ai-pipeline.md for which detection/action/captioning adapters are real vs. demo.
            </p>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
