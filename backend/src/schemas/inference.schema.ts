import { z } from "zod";

export const ingestDetectionsSchema = z.object({
  cameraId: z.string().min(1),
  mode: z.enum(["REAL", "DEMO"]),
  detections: z
    .array(
      z.object({
        objectLabel: z.string().min(1),
        confidence: z.number().min(0).max(1),
        boundingBox: z.array(z.number()).length(4),
        // offset: true accepts both "...Z" and "...+00:00" — Python's datetime.isoformat()
        // (used by ai-service) emits the latter.
        frameTimestamp: z.string().datetime({ offset: true }),
      })
    )
    .min(1),
});

export const ingestActionSchema = z.object({
  cameraId: z.string().min(1),
  mode: z.enum(["REAL", "DEMO"]),
  label: z.string().min(1),
  confidence: z.number().min(0).max(1),
  description: z.string().max(2000).optional(),
  // offset: true accepts both "...Z" and "...+00:00" — Python's datetime.isoformat()
  // (used by ai-service) emits the latter.
  windowStart: z.string().datetime({ offset: true }),
  windowEnd: z.string().datetime({ offset: true }),
  /** Raw 0.0–1.0 threat/escalation score computed by ai-service's ThreatAssessmentService. */
  threatScore: z.number().min(0).max(1),
  /** Human-readable rationale from the AI service, shown on the alert/incident. */
  rationale: z.string().max(2000).optional(),
});

export type IngestDetectionsInput = z.infer<typeof ingestDetectionsSchema>;
export type IngestActionInput = z.infer<typeof ingestActionSchema>;
