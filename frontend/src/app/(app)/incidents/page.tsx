"use client";

import useSWR from "swr";
import { Topbar } from "@/components/layout/Topbar";
import { Card, CardBody } from "@/components/ui/Card";
import { SeverityBadge, ModeBadge } from "@/components/ui/Badge";
import { api, fetcher } from "@/lib/api";
import { formatDateTime, incidentStatusLabels } from "@/lib/style";
import type { Incident } from "@/lib/types";


export default function IncidentsPage() {
  const { data, isLoading } = useSWR<{ incidents: Incident[] }>("/incidents", fetcher, { refreshInterval: 15000 });
  const incidents = data?.incidents ?? [];

  return (
    <div>
      <Topbar title="Incidents" description="Aggregated, reviewable security events" />

      <div className="space-y-3 p-6">
        {isLoading && <p className="text-sm text-slate-500">Loading...</p>}
        {!isLoading && incidents.length === 0 && (
          <Card>
            <CardBody className="text-sm text-slate-500">
              No incidents recorded yet. HIGH/CRITICAL alerts are automatically escalated into incidents.
            </CardBody>
          </Card>
        )}

        {incidents.map((incident) => (
          <a key={incident.id} href={`/incidents/${incident.id}`}>
            <Card className="transition-colors hover:border-blue-500/30">
              <CardBody className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <div className="mb-1 flex items-center gap-2">
                    <SeverityBadge severity={incident.severity} />
                    {incident.isDemo && <ModeBadge mode="DEMO" />}
                    <span className="text-[11px] font-medium text-slate-500">
                      {incidentStatusLabels[incident.reviewStatus]}
                    </span>
                  </div>
                  <p className="truncate font-semibold text-white">{incident.title}</p>
                  {incident.aiDescription && (
                    <p className="truncate text-sm text-slate-400">{incident.aiDescription}</p>
                  )}
                </div>
                <span className="shrink-0 text-xs text-slate-500">{formatDateTime(incident.createdAt)}</span>
              </CardBody>
            </Card>
          </a>
        ))}
      </div>
    </div>
  );
}
