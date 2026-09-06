import { z } from "zod";

export const ALERT_SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const;
export const ALERT_STATUSES = ["NEW", "REVIEWED", "DISMISSED", "ESCALATED"] as const;

export const listAlertsQuerySchema = z.object({
  severity: z.enum(ALERT_SEVERITIES).optional(),
  status: z.enum(ALERT_STATUSES).optional(),
  cameraId: z.string().optional(),
  limit: z.coerce.number().int().min(1).max(200).default(50),
});

export const updateAlertStatusSchema = z.object({
  status: z.enum(ALERT_STATUSES),
});

export type ListAlertsQuery = z.infer<typeof listAlertsQuerySchema>;
