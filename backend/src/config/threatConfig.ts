/**
 * Central, backend-owned threat-scoring thresholds. The AI service computes a raw
 * 0.0–1.0 threat/escalation score per docs/ai-pipeline.md; the backend — not the
 * frontend — is solely responsible for turning that score into a severity level and
 * deciding whether an Alert is warranted. Keeping this here (not hardcoded in the
 * dashboard) means thresholds can later move into the Settings page/DB without any
 * frontend change.
 */
export const THREAT_THRESHOLDS = {
  LOW: 0.2,
  MEDIUM: 0.4,
  HIGH: 0.65,
  CRITICAL: 0.85,
} as const;

export type Severity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

/** Below LOW, no alert is raised at all — the action is logged but not escalated. */
export function scoreToSeverity(score: number): Severity | null {
  if (score >= THREAT_THRESHOLDS.CRITICAL) return "CRITICAL";
  if (score >= THREAT_THRESHOLDS.HIGH) return "HIGH";
  if (score >= THREAT_THRESHOLDS.MEDIUM) return "MEDIUM";
  if (score >= THREAT_THRESHOLDS.LOW) return "LOW";
  return null;
}
