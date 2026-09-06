import { prisma } from "../lib/prisma";
import { broadcast } from "../websocket";
import { evaluateAction } from "./threatEngine.service";
import type { IngestActionInput, IngestDetectionsInput } from "../schemas/inference.schema";

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
    },
  });

  broadcast("action.detected", action);

  const result = await evaluateAction(action);
  return { action, ...result };
}
