import { z } from "zod";

export const INCIDENT_STATUSES = ["UNREVIEWED", "UNDER_REVIEW", "CONFIRMED", "DISMISSED"] as const;
export const SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const;

export const listIncidentsQuerySchema = z.object({
  severity: z.enum(SEVERITIES).optional(),
  reviewStatus: z.enum(INCIDENT_STATUSES).optional(),
  limit: z.coerce.number().int().min(1).max(200).default(50),
});

export const updateIncidentSchema = z.object({
  reviewStatus: z.enum(INCIDENT_STATUSES),
});

export type ListIncidentsQuery = z.infer<typeof listIncidentsQuerySchema>;
