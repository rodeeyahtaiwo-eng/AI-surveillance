import type { AlertStatus, CameraStatus, IncidentStatus, Severity } from "./types";

// Colors come from the dataviz skill's fixed status palette (good/warning/serious/
// critical), mapped onto LOW/MEDIUM/HIGH/CRITICAL — see tailwind.config.ts "severity".
// Status color is always paired with the text label, never carries meaning alone.
export const severityStyles: Record<Severity, { text: string; bg: string; dot: string }> = {
  LOW: { text: "text-severity-low", bg: "bg-severity-low/10 border-severity-low/30", dot: "bg-severity-low" },
  MEDIUM: {
    text: "text-severity-medium",
    bg: "bg-severity-medium/10 border-severity-medium/30",
    dot: "bg-severity-medium",
  },
  HIGH: { text: "text-severity-high", bg: "bg-severity-high/10 border-severity-high/30", dot: "bg-severity-high" },
  CRITICAL: {
    text: "text-severity-critical",
    bg: "bg-severity-critical/10 border-severity-critical/30",
    dot: "bg-severity-critical",
  },
};

export const cameraStatusStyles: Record<CameraStatus, { text: string; dot: string; label: string }> = {
  ONLINE: { text: "text-severity-low", dot: "bg-severity-low", label: "LIVE" },
  OFFLINE: { text: "text-slate-500", dot: "bg-slate-500", label: "OFFLINE" },
  ERROR: { text: "text-severity-critical", dot: "bg-severity-critical", label: "ERROR" },
  PROCESSING: { text: "text-sky-400", dot: "bg-sky-400", label: "PROCESSING" },
};

export const alertStatusLabels: Record<AlertStatus, string> = {
  NEW: "New",
  REVIEWED: "Reviewed",
  DISMISSED: "Dismissed",
  ESCALATED: "Escalated",
};

export const incidentStatusLabels: Record<IncidentStatus, string> = {
  UNREVIEWED: "Unreviewed",
  UNDER_REVIEW: "Under Review",
  CONFIRMED: "Confirmed",
  DISMISSED: "Dismissed",
};

export function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

// Staleness-aware threat display (design-reviewed "Option E") — presentation only. An
// Alert record is never mutated, resolved, or expired anywhere in the backend; this is
// purely how the frontend describes the age of the *existing* `Alert.createdAt` value,
// so a CRITICAL alert from minutes ago doesn't read as an ongoing current threat.
//
// Boundary chosen from the system's own existing timing, not arbitrarily: 120s is 20x
// SEQUENCE_WINDOW_SECONDS (6s) — if a threat condition were still actually present, the
// pipeline's own cadence would have produced a fresh alert well within that window.
// Going two full minutes without a new one is a meaningful "this has gone quiet" signal.
export const ALERT_STALENESS_SECONDS = 120;

/** Renders how long ago `iso` was, for display only — never used in scoring/persistence. */
export function formatRelativeTime(iso: string, now: Date = new Date()): string {
  const seconds = Math.max(0, Math.floor((now.getTime() - new Date(iso).getTime()) / 1000));
  if (seconds < 10) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours} hour${hours === 1 ? "" : "s"} ago`;
}

/** True once an alert is older than ALERT_STALENESS_SECONDS — display-only judgment,
 * never written back to the Alert record and never affects scoring/notifications. */
export function isAlertStale(iso: string, now: Date = new Date()): boolean {
  const seconds = (now.getTime() - new Date(iso).getTime()) / 1000;
  return seconds > ALERT_STALENESS_SECONDS;
}

// Staleness-aware live detection display (Phase 2P) — presentation only, mirrors
// isAlertStale() above exactly. Fixes a real bug (docs/phase2o-live-system-audit.md):
// the "Objects detected" panel used to keep the last 8 raw detection.created events
// with no time-based expiry at all, so a one-frame false positive (e.g. "toothbrush")
// stayed visible until 8 *newer* events arrived — which could take much longer than 8
// frames' worth of wall-clock time, or never happen if the scene went quiet.
//
// Boundary chosen from the system's own measured live timing, not arbitrarily: Phase
// 2O measured the ACTUAL achieved frame interval in a real live session at ~2.4s
// (video-processing's configured SAMPLE_FPS=2 / 0.5s interval is a floor on the sleep
// between frames, not the total cycle time -- it doesn't account for synchronous
// inference latency). 8 seconds is a little over 3x that measured interval: enough
// margin that a genuinely-still-present object survives a slow or skipped processing
// cycle without flickering out, short enough that a one-frame hallucination is gone
// within a handful of seconds instead of lingering indefinitely. Detection records
// themselves are never deleted or mutated in the database -- this only affects what
// the live panel currently renders.
export const DETECTION_STALENESS_SECONDS = 8;

/** True once a detection's frameTimestamp is older than DETECTION_STALENESS_SECONDS.
 * Display-only -- never affects what's persisted or broadcast, only what a live view
 * currently renders as "still visible". */
export function isDetectionStale(frameTimestampIso: string, now: Date = new Date()): boolean {
  const seconds = (now.getTime() - new Date(frameTimestampIso).getTime()) / 1000;
  return seconds > DETECTION_STALENESS_SECONDS;
}

// Phase 2AJ — surfaces the existing Phase 2T temporal-prediction sentence that
// ai-service's RuleBasedThreatEngine already appends to `rationale`, e.g. "... Temporal
// context: current action is 'standing'; model predicts 'standing' next (confidence
// 1.00, based on 6 prior observations for this camera)." Pure text extraction, not a
// re-derivation: finds the literal marker ai-service's own (unmodified) pipeline.py
// always emits and returns everything from it onward, verbatim. Returns null when
// there's no rationale yet (a pre-migration historical row) or no prediction was
// available for that window (e.g. cold start, or ai-service running a different
// TEMPORAL_PREDICTION_ADAPTER) -- both are honest "nothing to show" cases, never
// fabricated.
const TEMPORAL_CONTEXT_MARKER = "Temporal context:";

export function extractTemporalContext(rationale: string | null | undefined): string | null {
  if (!rationale) return null;
  const index = rationale.indexOf(TEMPORAL_CONTEXT_MARKER);
  if (index === -1) return null;
  return rationale.slice(index + TEMPORAL_CONTEXT_MARKER.length).trim();
}

// Phase 2AF — presentation-only mirror of backend/src/config/threatConfig.ts's
// THREAT_THRESHOLDS/scoreToSeverity(). Fixes the sibling of the Phase 2AE "Threat
// score" bug: "Threat level" was reading latestAlert.severity, which only updates when
// a NEW Alert is created (score clears the LOW threshold, 0.2) -- so the badge froze at
// whatever severity the last alert-worthy window had (e.g. MEDIUM) while the "Threat
// score" field (already fixed to read the live latestAction.threatScoreHint) moved
// freely underneath it, producing mismatched combinations like a 0.08 score still
// showing a MEDIUM badge. This does NOT change who decides whether an Alert/Incident/
// notification fires -- that remains exclusively backend/src/services/
// threatEngine.service.ts, keyed off the persisted Alert record, completely
// independent of this display-only computation. If the backend's thresholds ever
// change, this copy must be updated to match -- there is no shared package between
// frontend and backend to import it from directly (see package.json workspaces; frontend
// and backend build/bundle separately).
const THREAT_THRESHOLDS = { LOW: 0.2, MEDIUM: 0.4, HIGH: 0.65, CRITICAL: 0.85 } as const;

/** Mirrors the backend's scoreToSeverity() exactly, for live display only. Returns null
 * below the LOW threshold, just like the backend (no alert would be raised either). */
export function scoreToSeverity(score: number): Severity | null {
  if (score >= THREAT_THRESHOLDS.CRITICAL) return "CRITICAL";
  if (score >= THREAT_THRESHOLDS.HIGH) return "HIGH";
  if (score >= THREAT_THRESHOLDS.MEDIUM) return "MEDIUM";
  if (score >= THREAT_THRESHOLDS.LOW) return "LOW";
  return null;
}
