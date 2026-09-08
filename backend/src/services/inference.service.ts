import { prisma } from "../lib/prisma";
import { broadcast } from "../websocket";
import { evaluateAction } from "./threatEngine.service";
import type { IngestActionInput, IngestDetectionsInput } from "../schemas/inference.schema";

// Phase 2AK — read-only history lookup for the Markov temporal predictor's bootstrap
// (see ai-service/app/services/pipeline.py's maybe_bootstrap_temporal_predictor()).
// A generous but bounded cap, not unbounded: this project's busiest real camera has
// ~2200 logged Action rows after weeks of testing — 5000 leaves comfortable headroom
// without risking an unbounded query on a camera with an unexpectedly huge history.
const ACTION_HISTORY_MAX_ROWS = 5000;

/** Ordered oldest-to-newest, label + windowStart only — exactly what the Markov
 * predictor's existing observe() loop needs, nothing more. */
export async function getActionHistory(cameraId: string) {
  return prisma.action.findMany({
    where: { cameraId },
    select: { label: true, windowStart: true },
    orderBy: { windowStart: "asc" },
    take: ACTION_HISTORY_MAX_ROWS,
  });
}

/** Persists a batch of object-detection results from ai-service and broadcasts each. */
export async function ingestDetections(input: IngestDetectionsInput) {
  const created = await prisma.$transaction(
    input.detections.map((d) =>
      prisma.detection.create({
        data: {
          cameraId: input.cameraId,
          objectLabel: d.objectLabel,
          confidence: d.confidence,
          boundingBox: JSON.stringify(d.boundingBox),
          frameTimestamp: new Date(d.frameTimestamp),
          mode: input.mode,
        },
      })
    )
  );

  for (const detection of created) broadcast("detection.created", detection);
  return created;
}

/**
 * Persists a recognized action/caption result from ai-service, broadcasts it, and hands
 * it to the Threat Engine to decide whether it warrants an Alert/Incident.
 */
export async function ingestAction(input: IngestActionInput) {
  const action = await prisma.action.create({
    data: {
      cameraId: input.cameraId,
      label: input.label,
      confidence: input.confidence,
      description: input.description,
      windowStart: new Date(input.windowStart),
      windowEnd: new Date(input.windowEnd),
      mode: input.mode,
      threatScoreHint: input.threatScore,
      // Phase 2AJ — was already sent by ai-service and validated by
      // inference.schema.ts, but silently dropped here before this line existed.
      // Display-only: never read by evaluateAction()/the Threat Engine below, so
      // storing it cannot affect threat_score, severity, or alert/incident creation.
      rationale: input.rationale,
    },
  });

  broadcast("action.detected", action);

  const result = await evaluateAction(action);
  return { action, ...result };
}
