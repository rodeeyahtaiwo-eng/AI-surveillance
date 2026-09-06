import type { Alert, Severity } from "./types";

// Phase 2AG — audio cue for a NEW alert.created event, frontend-only. Purely additive:
// nothing in ai-service or backend detection/scoring is touched by this file, and
// nothing here can influence what severity/type an Alert actually has -- it only
// decides whether to play a sound for an alert the backend already created.
//
// Trigger chosen: severity >= MEDIUM, OR type === "fighting_candidate" specifically.
// Severity alone already covers every real fighting_candidate alert observed in this
// project (its base score of 0.70 alone already exceeds the MEDIUM threshold of 0.4,
// so it can never itself create a below-MEDIUM alert) -- the explicit label check is
// kept anyway as a deliberate, low-cost belt-and-suspenders case: it means an operator
// is guaranteed to hear this specific, highest-severity label even if a future scoring
// change ever altered its base weight. LOW-only alerts (e.g. a transient "running"
// misclassification) stay silent, matching the same LOW/MEDIUM distinction the
// dashboard's own severity badges already draw.
const SEVERITY_RANK: Record<Severity, number> = { LOW: 1, MEDIUM: 2, HIGH: 3, CRITICAL: 4 };

export function shouldPlayAlertSound(alert: Pick<Alert, "type" | "severity">): boolean {
  if (alert.type === "fighting_candidate") return true;
  return SEVERITY_RANK[alert.severity] >= SEVERITY_RANK.MEDIUM;
}

/** Synthesizes a short two-beep audio cue via the Web Audio API -- no audio asset to
 * bundle or host. Never throws: audio is a nice-to-have and must never break alert
 * handling (a missing/blocked AudioContext -- e.g. in a test environment, or before the
 * user has interacted with the page yet, per browsers' autoplay policy -- is silently
 * a no-op, not an error). */
export function playAlertSound(): void {
  if (typeof window === "undefined") return;
  try {
    const AudioContextCtor: typeof AudioContext | undefined =
      window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioContextCtor) return;

    const ctx = new AudioContextCtor();
    const now = ctx.currentTime;

    for (const startOffset of [0, 0.22]) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.value = 880;
      gain.gain.setValueAtTime(0.0001, now + startOffset);
      gain.gain.exponentialRampToValueAtTime(0.3, now + startOffset + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + startOffset + 0.18);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now + startOffset);
      osc.stop(now + startOffset + 0.2);
    }

    // Don't accumulate open AudioContexts across many alerts arriving over a session.
    setTimeout(() => {
      ctx.close().catch(() => {});
    }, 500);
  } catch {
    // Never let a sound failure break alert handling.
  }
}
