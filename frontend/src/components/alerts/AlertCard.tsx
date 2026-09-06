"use client";

import { Eye, CheckCircle2, XCircle, ArrowUpCircle } from "lucide-react";
import { Card, CardBody } from "@/components/ui/Card";
import { SeverityBadge, ModeBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { formatDateTime } from "@/lib/style";
import type { Alert } from "@/lib/types";

export function AlertCard({
  alert,
  onStatusChange,
}: {
  alert: Alert;
  onStatusChange: (status: Alert["status"]) => void;
}) {
  return (
    <Card>
      <CardBody className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="mb-1 flex items-center gap-2">
              <SeverityBadge severity={alert.severity} />
              <ModeBadge mode={alert.mode} />
              {alert.status !== "NEW" && (
                <span className="text-[11px] font-medium text-slate-500">{alert.status}</span>
              )}
            </div>
            <p className="font-semibold text-white">{humanizeType(alert.type)}</p>
          </div>
          <span className="text-xs text-slate-500">{formatDateTime(alert.createdAt)}</span>
        </div>

        <p className="text-sm text-slate-300">{alert.description}</p>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
          <span>
            Camera: <span className="text-slate-300">{alert.camera?.name ?? alert.cameraId}</span>
          </span>
          <span>
            Location: <span className="text-slate-300">{alert.camera?.location ?? "—"}</span>
          </span>
          <span>
            Confidence: <span className="text-slate-300">{Math.round(alert.confidence * 100)}%</span>
          </span>
          {alert.threatScore != null && (
            <span>
              Threat score: <span className="text-slate-300">{alert.threatScore.toFixed(2)}</span>
            </span>
          )}
        </div>

        <div className="flex flex-wrap gap-2 pt-1">
          {alert.incidentId && (
            <Button variant="secondary" onClick={() => (window.location.href = `/incidents/${alert.incidentId}`)}>
              <Eye className="h-4 w-4" /> View incident
            </Button>
          )}
          <Button variant="secondary" onClick={() => onStatusChange("REVIEWED")} disabled={alert.status === "REVIEWED"}>
            <CheckCircle2 className="h-4 w-4" /> Mark as reviewed
          </Button>
          <Button variant="ghost" onClick={() => onStatusChange("DISMISSED")} disabled={alert.status === "DISMISSED"}>
            <XCircle className="h-4 w-4" /> Dismiss
          </Button>
          <Button variant="danger" onClick={() => onStatusChange("ESCALATED")} disabled={alert.status === "ESCALATED"}>
            <ArrowUpCircle className="h-4 w-4" /> Escalate
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}

function humanizeType(type: string) {
  return type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
