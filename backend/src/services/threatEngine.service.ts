import type { Action } from "@prisma/client";
import { env } from "../config/env";
import { prisma } from "../lib/prisma";
import { scoreToSeverity } from "../config/threatConfig";
import { broadcast } from "../websocket";
import { dispatchNotification } from "./notification";
import { logger } from "../utils/logger";

// Phase 2AG — a short, explicit action-label tag prepended to the ALERT's description
// only (never the underlying Action.description, which stays exactly what the caption
// adapter produced — this never touches ai-service's caption generation or grounding
// text). Exists because BLIP is a general-purpose image captioner, not trained on this
// project's action-recognition vocabulary, and is not reliably going to say "fighting"
// on its own (see docs/ai-pipeline.md Stage 3) — the geometry-heuristic's own label is
// already a real, structured signal at this point; this just surfaces it in the text an
// operator actually reads. Deliberately scoped to fighting_candidate only, per explicit
// request — not generalized to every label.
const ACTION_DESCRIPTION_TAGS: Partial<Record<string, string>> = {
  fighting_candidate: "Fighting detected",
};

function buildAlertDescription(action: Action): string {
  const base = action.description ?? `Potential ${action.label} activity detected.`;
  const tag = ACTION_DESCRIPTION_TAGS[action.label];
  return tag ? `${tag} — ${base}` : base;
}

/**
 * The Threat Engine: turns an AI-computed threat score into a severity level and, where
 * warranted, an Alert (and for HIGH/CRITICAL, an Incident + notification). This is
 * intentionally backend-owned logic — see docs/ai-pipeline.md "Stage 4" and
 * config/threatConfig.ts. The frontend only ever renders what this produces.
 */
export async function evaluateAction(action: Action) {
  const severity = scoreToSeverity(action.threatScoreHint ?? 0);
  if (!severity) {
    logger.debug("Threat score below alert threshold — no alert raised", {
      actionId: action.id,
      score: action.threatScoreHint,
    });
    return null;
  }

  const alert = await prisma.alert.create({
    data: {
      cameraId: action.cameraId,
      actionId: action.id,
      type: action.label,
      severity,
      confidence: action.confidence,
      description: buildAlertDescription(action),
      mode: action.mode,
      threatScore: action.threatScoreHint,
      status: "NEW",
    },
    include: { camera: true },
  });

  broadcast("alert.created", alert);
  logger.info(`Alert created: ${alert.type} (${alert.severity})`, { alertId: alert.id });

  let incident = null;
  if (severity === "HIGH" || severity === "CRITICAL") {
    incident = await prisma.incident.create({
      data: {
        title: `${alert.type} — ${alert.camera.name}`,
        eventType: alert.type,
        severity: alert.severity,
        confidence: alert.confidence,
        aiDescription: alert.description,
        startTime: action.windowStart,
        endTime: action.windowEnd,
        isDemo: alert.mode === "DEMO",
        reviewStatus: "UNREVIEWED",
        alerts: { connect: { id: alert.id } },
      },
    });
    broadcast("incident.created", incident);
    logger.info(`Incident created for ${severity} alert`, { incidentId: incident.id });
  }

  // Phase 2AO Stage 2 — real email for HIGH/CRITICAL (see
  // services/notification/emailProvider.ts, verified with a real send in Stage 1).
  // Extended to MEDIUM as a follow-up: this gate is deliberately kept SEPARATE from the
  // Incident-creation gate above, which stays HIGH/CRITICAL-only and untouched — per
  // explicit request, only which severities trigger a *notification* changed here, not
  // scoreToSeverity()/threatConfig.ts's thresholds and not Incident-creation policy. A
  // MEDIUM alert now emails but does NOT get an Incident. This is the ONLY
  // dispatchNotification() call site in the app — LOW alerts still never notify (they
  // stop at Alert.create() above), so there's no other "still uses LOG" path to
  // preserve. If EMAIL isn't actually configured (SMTP_USER/SMTP_PASS unset),
  // notification/index.ts's existing "not configured" fallback still applies here
  // unchanged — this call doesn't newly assume delivery succeeds, it just asks for the
  // real channel instead of the dev-only one.
  if (severity === "MEDIUM" || severity === "HIGH" || severity === "CRITICAL") {
    await dispatchNotification({
      alertId: alert.id,
      channel: "EMAIL",
      recipient: env.NOTIFY_EMAIL_TO ?? "security-team@example.com",
      subject: `[${alert.severity}] ${alert.type} at ${alert.camera.name}`,
      message: [
        `Camera: ${alert.camera.name}`,
        `Severity: ${alert.severity} (threat score ${alert.threatScore?.toFixed(2) ?? "n/a"})`,
        `Detected: ${alert.createdAt.toISOString()}`,
        "",
        alert.description,
      ].join("\n"),
    });
  }

  return { alert, incident };
}
