"use client";

import { useParams, useRouter } from "next/navigation";
import useSWR, { useSWRConfig } from "swr";
import { ArrowLeft, FileVideo } from "lucide-react";
import { Topbar } from "@/components/layout/Topbar";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { SeverityBadge, ModeBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { api, fetcher } from "@/lib/api";
import { formatDateTime, incidentStatusLabels } from "@/lib/style";
import type { Incident, IncidentStatus } from "@/lib/types";

const STATUSES: IncidentStatus[] = ["UNREVIEWED", "UNDER_REVIEW", "CONFIRMED", "DISMISSED"];

export default function IncidentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { data, mutate: mutateThis } = useSWR<{ incident: Incident }>(`/incidents/${id}`, fetcher);
  const { mutate } = useSWRConfig();
  const incident = data?.incident;

  async function updateStatus(reviewStatus: IncidentStatus) {
    await api.patch(`/incidents/${id}`, { reviewStatus });
    mutateThis();
    mutate("/incidents");
  }

  if (!incident) {
    return (
      <div>
        <Topbar title="Incident" />
        <div className="p-6 text-sm text-slate-500">Loading...</div>
      </div>
    );
  }

  return (
    <div>
      <Topbar title={incident.title} description={`Incident ${incident.id}`} />

      <div className="space-y-4 p-6">
        <Button variant="ghost" onClick={() => router.push("/incidents")}>
          <ArrowLeft className="h-4 w-4" /> Back to Incidents
        </Button>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="space-y-4 lg:col-span-2">
            <Card>
              <CardHeader className="flex items-center gap-2">
                <SeverityBadge severity={incident.severity} />
                {incident.isDemo && <ModeBadge mode="DEMO" />}
                <span className="text-xs text-slate-500">{incidentStatusLabels[incident.reviewStatus]}</span>
              </CardHeader>
              <CardBody className="space-y-4">
                <div className="flex h-64 items-center justify-center rounded-md border border-dashed border-surface-border bg-black/30 text-slate-600">
                  <div className="flex flex-col items-center gap-2 text-center">
                    <FileVideo className="h-8 w-8" />
                    <p className="max-w-xs text-xs text-slate-500">
                      {incident.videoSegments && incident.videoSegments.length > 0
                        ? `Evidence clip reference: ${incident.videoSegments[0].filePath}`
                        : "No evidence clip attached yet — video storage lands with the video-processing pipeline (Phase 7)."}
                    </p>
                  </div>
                </div>

                <div>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    AI-Generated Description
                  </p>
                  <p className="text-sm text-slate-300">
                    {incident.aiDescription ?? "No description available."}
                  </p>
                </div>

                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Event Type</p>
                    <p className="text-slate-300">{incident.eventType}</p>
                  </div>
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Confidence</p>
                    <p className="text-slate-300">{Math.round(incident.confidence * 100)}%</p>
                  </div>
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Start</p>
                    <p className="text-slate-300">{formatDateTime(incident.startTime)}</p>
                  </div>
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">End</p>
                    <p className="text-slate-300">{incident.endTime ? formatDateTime(incident.endTime) : "—"}</p>
                  </div>
                </div>
              </CardBody>
            </Card>

            <Card>
              <CardHeader>
                <p className="text-sm font-semibold text-white">Alert History</p>
              </CardHeader>
              <CardBody className="divide-y divide-surface-border p-0">
                {(incident.alerts?.length ?? 0) === 0 ? (
                  <p className="p-4 text-sm text-slate-500">No linked alerts.</p>
                ) : (
                  incident.alerts?.map((alert) => (
                    <div key={alert.id} className="flex items-center justify-between gap-3 px-4 py-3">
                      <div className="min-w-0">
                        <div className="mb-0.5 flex items-center gap-2">
                          <SeverityBadge severity={alert.severity} />
                          <span className="text-xs text-slate-500">{alert.type}</span>
                        </div>
                        <p className="truncate text-sm text-slate-300">{alert.description}</p>
                      </div>
                      <span className="shrink-0 text-xs text-slate-500">{formatDateTime(alert.createdAt)}</span>
                    </div>
                  ))
                )}
              </CardBody>
            </Card>
          </div>

          <div className="space-y-4">
            <Card>
              <CardHeader>
                <p className="text-sm font-semibold text-white">Administrator Review</p>
              </CardHeader>
              <CardBody className="space-y-2">
                {STATUSES.map((status) => (
                  <button
                    key={status}
                    onClick={() => updateStatus(status)}
                    className={`w-full rounded-md border px-3 py-2 text-left text-sm transition-colors ${
                      incident.reviewStatus === status
                        ? "border-blue-500/40 bg-blue-500/10 text-blue-300"
                        : "border-surface-border bg-white/5 text-slate-300 hover:bg-white/10"
                    }`}
                  >
                    {incidentStatusLabels[status]}
                  </button>
                ))}
              </CardBody>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
