import type { Action } from "@prisma/client";
import { prisma } from "../lib/prisma";
import { scoreToSeverity } from "../config/threatConfig";
import { broadcast } from "../websocket";
import { dispatchNotification } from "./notification";
import { logger } from "../utils/logger";

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
      description: action.description ?? `Potential ${action.label} activity detected.`,
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

    // Development notification provider (LOG) — see docs/setup.md for wiring a real
    // email/SMS/push provider via environment variables.
    await dispatchNotification({
      alertId: alert.id,
      channel: "LOG",
      recipient: "security-team@example.com",
      subject: `[${alert.severity}] ${alert.type} at ${alert.camera.name}`,
      message: alert.description,
    });
  }

  return { alert, incident };
}
