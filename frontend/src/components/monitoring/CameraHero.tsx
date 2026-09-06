"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import clsx from "clsx";
import { VideoOff, Wifi, Sparkles } from "lucide-react";
import type { Action, Alert, Camera, Detection } from "@/lib/types";
import {
  cameraStatusStyles,
  formatRelativeTime,
  isAlertStale,
  isDetectionStale,
  scoreToSeverity,
  severityStyles,
} from "@/lib/style";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { DemoBadge, ModeBadge, Pill, SeverityBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";

/**
 * The primary Live Monitoring hero: a large 16:9 video slot + a real-time AI info
 * panel. No browser-viewable video decode exists in this build yet (video-processing
 * only forwards frames to ai-service, not to the browser — see docs/architecture.md),
 * so the video slot always shows an honest state instead of a fake CCTV image. The
 * panel next to it is driven entirely by real data the backend has actually reported
 * (via WebSocket + the existing /api/alerts endpoint) — nothing here is fabricated; a
 * section reads "No data available" when nothing has come in yet.
 */
export function CameraHero({
  camera,
  recentDetections,
  latestAction,
  latestAlert,
  aiServiceReachable,
  backendReachable,
  wsConnected,
}: {
  camera: Camera;
  recentDetections: Detection[];
  latestAction: Action | null;
  latestAlert: Alert | null;
  aiServiceReachable: boolean;
  backendReachable: boolean;
  wsConnected: boolean;
}) {
  const statusStyle = cameraStatusStyles[camera.status];
  const isLive = camera.status === "ONLINE";
  // Presentation-only judgment of the existing Alert.createdAt — never mutates, never
  // resolves, never affects the Alert record itself (design-reviewed "Option E").
  const alertStale = latestAlert ? isAlertStale(latestAlert.createdAt) : false;

  // Phase 2AF — the live severity badge must derive from the SAME fresh source as the
  // "Threat score" field (latestAction.threatScoreHint), not from latestAlert.severity
  // — see scoreToSeverity()'s doc comment in lib/style.ts for the sibling bug this
  // fixes. null when there's no current action yet, or its score is below the LOW
  // threshold (matching the backend: no alert would be raised there either).
  const liveSeverity = latestAction?.threatScoreHint != null ? scoreToSeverity(latestAction.threatScoreHint) : null;

  // Ticks once a second so "Objects detected" re-evaluates staleness even when no new
  // WebSocket event has arrived — otherwise a stale entry would only disappear once a
  // fresher detection happened to trigger a React re-render (Phase 2P fix; see
  // lib/style.ts DETECTION_STALENESS_SECONDS for why 8s and why this is display-only).
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const freshDetections = recentDetections.filter((d) => !isDetectionStale(d.frameTimestamp, now));
  const objectCounts = new Map<string, number>();
  for (const d of freshDetections) objectCounts.set(d.objectLabel, (objectCounts.get(d.objectLabel) ?? 0) + 1);

  return (
    <Card>
      <CardHeader className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-lg font-semibold text-white">
            {camera.name} <span className="text-slate-500">—</span> {camera.location}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {camera.isDemo && <DemoBadge />}
          <span className={clsx("flex items-center gap-1.5 text-xs font-bold tracking-wide", statusStyle.text)}>
            <span className={clsx("h-2 w-2 rounded-full", statusStyle.dot, isLive && "animate-pulse")} />
            {statusStyle.label}
          </span>
          {aiServiceReachable && (
            <span className="flex items-center gap-1 rounded-md border border-severity-low/30 bg-severity-low/10 px-2 py-0.5 text-xs font-bold tracking-wide text-severity-low">
              <Sparkles className="h-3 w-3" /> AI ACTIVE
            </span>
          )}
        </div>
      </CardHeader>

      <CardBody className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        {/* Video area — proper 16:9, dominates the page. */}
        <div className="xl:col-span-2">
          <div className="relative aspect-video w-full overflow-hidden rounded-lg border border-surface-border bg-black/40">
            <VideoEmptyState camera={camera} />
          </div>
        </div>

        {/* AI information panel */}
        <div className="space-y-4">
          <InfoSection
            title="Current Activity"
            badge={latestAction ? <ModeBadge mode={latestAction.mode} /> : undefined}
          >
            <Row label="Objects detected">
              {objectCounts.size > 0 ? (
                <div className="flex flex-wrap justify-end gap-1">
                  {Array.from(objectCounts.entries()).map(([label, count]) => (
                    <Pill key={label}>
                      {label} × {count}
                    </Pill>
                  ))}
                </div>
              ) : (
                <Muted>No current detections</Muted>
              )}
            </Row>
            <Row label="Current action">
              {latestAction ? <span className="text-slate-200">{latestAction.label}</span> : <Muted>—</Muted>}
            </Row>
            <div>
              <p className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-500">AI Analysis</p>
              <p className="text-sm text-slate-300">
                {latestAction?.description ?? latestAlert?.description ?? "Monitoring..."}
              </p>
            </div>
          </InfoSection>

          <InfoSection
            title="Threat Assessment"
            badge={latestAlert ? <ModeBadge mode={latestAlert.mode} /> : undefined}
          >
            <Row label="Threat level">
              {/* Phase 2AF fix: derived from the same live latestAction.threatScoreHint
                  as "Threat score" above (via scoreToSeverity()), not latestAlert.severity
                  — that badge only updated when a NEW Alert was created, so it froze at
                  the last alert-worthy severity (e.g. MEDIUM) while the score underneath
                  it moved freely, producing mismatched combinations like a 0.08 score
                  still showing MEDIUM. See lib/style.ts's scoreToSeverity() doc comment. */}
              {liveSeverity ? (
                <SeverityBadge severity={liveSeverity} />
              ) : (
                <Muted>No active alert</Muted>
              )}
            </Row>
            <Row label="Threat score">
              {/* Phase 2AE fix: this must read the latest ACTION's live, per-window
                  score, not the latest ALERT's — an Alert is only created when a score
                  crosses scoreToSeverity's LOW threshold (0.2), so reading
                  latestAlert.threatScore made this field freeze at the last
                  alert-worthy value (e.g. a transient "running" misclassification's
                  0.30) through any number of subsequent lower-scoring windows,
                  including a correctly-computed 0.0 for a genuine no_activity window —
                  even though the backend was recomputing a fresh score every window the
                  whole time. latestAction updates on every action.detected broadcast,
                  unconditionally, so it always reflects the current window. */}
              {latestAction?.threatScoreHint != null ? (
                <span className="text-slate-200">{latestAction.threatScoreHint.toFixed(2)}</span>
              ) : (
                <Muted>—</Muted>
              )}
            </Row>
            <Row label="Alert status">
              {latestAlert ? <span className="text-slate-200">{latestAlert.status}</span> : <Muted>—</Muted>}
            </Row>
            {latestAlert && (
              <Row label={alertStale ? "Historical alert" : "Detected"}>
                {alertStale ? (
                  <span className="text-slate-400">
                    Historical alert — no recent threat signal ({formatRelativeTime(latestAlert.createdAt)})
                  </span>
                ) : (
                  <span className="text-slate-200">Detected {formatRelativeTime(latestAlert.createdAt)}</span>
                )}
              </Row>
            )}
          </InfoSection>

          <InfoSection title="System Status">
            <Row label="Camera">
              <span className={clsx("font-semibold", statusStyle.text)}>{statusStyle.label}</span>
            </Row>
            <Row label="AI service">
              <StatusPill ok={aiServiceReachable} />
            </Row>
            <Row label="Backend">
              <StatusPill ok={backendReachable} />
            </Row>
            <Row label="WebSocket">
              <StatusPill ok={wsConnected} />
            </Row>
          </InfoSection>
        </div>
      </CardBody>
    </Card>
  );
}

function VideoEmptyState({ camera }: { camera: Camera }) {
  if (camera.status === "ONLINE") {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
        <Wifi className="h-8 w-8 text-severity-low" />
        <p className="text-sm font-semibold text-slate-300">AI analysis active — no video preview</p>
        <p className="max-w-sm text-xs text-slate-500">
          This build forwards sampled frames from video-processing to the AI service for
          real analysis, but doesn&apos;t yet stream decoded video back to the browser.
          Detections and activity will still appear in the panel alongside as they
          happen.
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
      <VideoOff className="h-10 w-10 text-slate-600" />
      <p className="text-base font-semibold text-slate-300">CAMERA NOT CONNECTED</p>
      <p className="max-w-sm text-sm text-slate-500">No live video stream is currently available.</p>
      <Link href="/cameras">
        <Button variant="primary">Connect Camera</Button>
      </Link>
    </div>
  );
}

function InfoSection({
  title,
  badge,
  children,
}: {
  title: string;
  badge?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <p className="text-xs font-bold uppercase tracking-widest text-slate-500">{title}</p>
        {badge}
      </div>
      <div className="space-y-2 rounded-md border border-surface-border bg-white/[0.02] p-3">{children}</div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 text-sm">
      <span className="text-slate-500">{label}</span>
      {children}
    </div>
  );
}

function Muted({ children }: { children: React.ReactNode }) {
  return <span className="text-slate-600">{children}</span>;
}

function StatusPill({ ok }: { ok: boolean }) {
  return (
    <span className={clsx("flex items-center gap-1.5 text-xs font-semibold", ok ? "text-severity-low" : "text-severity-critical")}>
      <span className={clsx("h-1.5 w-1.5 rounded-full", ok ? "bg-severity-low" : "bg-severity-critical")} />
      {ok ? "Connected" : "Unavailable"}
    </span>
  );
}
