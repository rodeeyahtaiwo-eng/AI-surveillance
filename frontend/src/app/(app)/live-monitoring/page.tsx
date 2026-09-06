"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { Topbar } from "@/components/layout/Topbar";
import { CameraHero } from "@/components/monitoring/CameraHero";
import { CameraFeedCard } from "@/components/monitoring/CameraFeedCard";
import { Card, CardBody } from "@/components/ui/Card";
import { api, fetcher } from "@/lib/api";
import { useRealtime } from "@/lib/useRealtime";
import type { Action, Alert, Camera, Detection, SystemStatus } from "@/lib/types";

interface CameraActivity {
  detections: Detection[];
  action: Action | null;
}

// Phase 2P: this is now a memory/array-size safety cap only, not the mechanism that
// decides what's "current" -- that's CameraHero's time-based staleness filter
// (lib/style.ts DETECTION_STALENESS_SECONDS). Sized generously above what a single
// busy frame or two could plausibly produce, so a real burst of distinct objects isn't
// truncated before the staleness filter ever gets a chance to apply.
const MAX_RECENT_DETECTIONS = 50;

export default function LiveMonitoringPage() {
  const { data: camerasRes } = useSWR<{ cameras: Camera[] }>("/cameras", fetcher, { refreshInterval: 10000 });
  const { data: status } = useSWR<SystemStatus>("/system/status", fetcher, { refreshInterval: 15000 });

  const cameras = camerasRes?.cameras ?? [];
  // "Primary" camera = the one featured in the hero. With today's single-camera demo
  // setup this is simply the only camera; multiple cameras are still fully supported —
  // any others render below in a compact grid, see docs/architecture.md.
  const primary = cameras[0];
  const secondary = cameras.slice(1);

  const [activityByCamera, setActivityByCamera] = useState<Record<string, CameraActivity>>({});
  const [latestAlertByCamera, setLatestAlertByCamera] = useState<Record<string, Alert>>({});

  // Seed the Threat Assessment panel with whatever the backend already knows (via the
  // existing GET /api/alerts?cameraId= endpoint) so the page isn't blank before any new
  // WebSocket event arrives.
  const { data: primaryAlerts } = useSWR<{ alerts: Alert[] }>(
    primary ? `/alerts?cameraId=${primary.id}&limit=1` : null,
    fetcher
  );
  useEffect(() => {
    const alert = primaryAlerts?.alerts?.[0];
    if (alert) setLatestAlertByCamera((prev) => ({ ...prev, [alert.cameraId]: alert }));
  }, [primaryAlerts]);

  const { connected: wsConnected } = useRealtime((event) => {
    const payload = event.payload as { cameraId?: string } | undefined;
    const cameraId = payload?.cameraId;
    if (!cameraId) return;

    if (event.type === "detection.created") {
      const detection = event.payload as Detection;
      setActivityByCamera((prev) => {
        const existing = prev[cameraId] ?? { detections: [], action: null };
        return {
          ...prev,
          [cameraId]: { ...existing, detections: [...existing.detections, detection].slice(-MAX_RECENT_DETECTIONS) },
        };
      });
    }

    if (event.type === "action.detected") {
      const action = event.payload as Action;
      setActivityByCamera((prev) => ({
        ...prev,
        [cameraId]: { detections: prev[cameraId]?.detections ?? [], action },
      }));
    }

    if (event.type === "alert.created" || event.type === "alert.updated") {
      const alert = event.payload as Alert;
      setLatestAlertByCamera((prev) => ({ ...prev, [cameraId]: alert }));
    }
  });

  const backendReachable = !!status;
  const aiServiceReachable = status?.aiService.reachable ?? false;

  return (
    <div>
      <Topbar title="Live Monitoring" description="What is happening right now" />

      <div className="space-y-6 p-6">
        {!primary ? (
          <Card>
            <CardBody className="text-sm text-slate-500">
              No camera registered yet. Add one from the{" "}
              <a href="/cameras" className="text-blue-400 hover:underline">
                Cameras
              </a>{" "}
              page to begin monitoring.
            </CardBody>
          </Card>
        ) : (
          <CameraHero
            camera={primary}
            recentDetections={activityByCamera[primary.id]?.detections ?? []}
            latestAction={activityByCamera[primary.id]?.action ?? null}
            latestAlert={latestAlertByCamera[primary.id] ?? null}
            aiServiceReachable={aiServiceReachable}
            backendReachable={backendReachable}
            wsConnected={wsConnected}
          />
        )}

        {secondary.length > 0 && (
          <div>
            <h2 className="mb-3 text-sm font-semibold text-white">Other Cameras</h2>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
              {secondary.map((camera) => (
                <CameraFeedCard key={camera.id} camera={camera} variant="full" />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
