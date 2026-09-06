"use client";

import { Video, VideoOff } from "lucide-react";
import clsx from "clsx";
import type { Camera } from "@/lib/types";
import { cameraStatusStyles, severityStyles } from "@/lib/style";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { DemoBadge, Pill } from "@/components/ui/Badge";

/**
 * Renders a camera's feed slot. Video/demo streaming (Phase 7) is not implemented yet —
 * this honestly shows a placeholder instead of faking a live decode. Once video-processing
 * lands, the placeholder block is swapped for an actual <video>/<canvas> element without
 * changing this component's props contract.
 */
export function CameraFeedCard({
  camera,
  variant = "compact",
  latestActivity,
  detectedObjects,
  threatLevel,
}: {
  camera: Camera;
  variant?: "compact" | "full";
  latestActivity?: string;
  detectedObjects?: string[];
  threatLevel?: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | null;
}) {
  const statusStyle = cameraStatusStyles[camera.status];
  const isLive = camera.status === "ONLINE";

  return (
    <Card>
      <CardHeader className="flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold text-white">{camera.name}</p>
          <p className="text-xs text-slate-500">{camera.location}</p>
        </div>
        <div className="flex items-center gap-2">
          {camera.isDemo && <DemoBadge />}
          <span className={clsx("flex items-center gap-1.5 text-xs font-semibold", statusStyle.text)}>
            <span className={clsx("h-1.5 w-1.5 rounded-full", statusStyle.dot, isLive && "animate-pulse")} />
            {statusStyle.label}
          </span>
        </div>
      </CardHeader>

      <CardBody className="space-y-3">
        <div
          className={clsx(
            "flex items-center justify-center rounded-md border border-dashed border-surface-border bg-black/30 text-slate-600",
            variant === "full" ? "h-56" : "h-32"
          )}
        >
          <div className="flex flex-col items-center gap-2 text-center">
            {isLive ? <Video className="h-6 w-6" /> : <VideoOff className="h-6 w-6" />}
            <p className="max-w-[200px] text-[11px] leading-tight text-slate-500">
              {camera.isDemo
                ? "Demo camera — video playback lands in Phase 7 (video-processing)."
                : isLive
                ? "Live decode not yet wired up — see docs/demo.md."
                : "Camera offline."}
            </p>
          </div>
        </div>

        {variant === "full" && (
          <div className="space-y-2 text-xs">
            <div>
              <p className="mb-1 font-medium uppercase tracking-wide text-slate-500">Activity</p>
              <p className="text-slate-300">
                {latestActivity ?? "No recent activity analyzed for this camera."}
              </p>
            </div>
            <div>
              <p className="mb-1 font-medium uppercase tracking-wide text-slate-500">Detected objects</p>
              <div className="flex flex-wrap gap-1">
                {detectedObjects && detectedObjects.length > 0 ? (
                  detectedObjects.map((obj) => <Pill key={obj}>{obj}</Pill>)
                ) : (
                  <span className="text-slate-600">None</span>
                )}
              </div>
            </div>
            <div className="flex items-center justify-between">
              <span className="font-medium uppercase tracking-wide text-slate-500">Threat</span>
              <span className={clsx("font-semibold", threatLevel ? severityStyles[threatLevel].text : "text-slate-600")}>
                {threatLevel ?? "—"}
              </span>
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  );
}
