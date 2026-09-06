import { z } from "zod";

export const CAMERA_STATUSES = ["ONLINE", "OFFLINE", "ERROR", "PROCESSING"] as const;

export const createCameraSchema = z.object({
  name: z.string().min(1).max(120),
  location: z.string().min(1).max(200),
  streamUrl: z.string().min(1).max(500),
  description: z.string().max(1000).optional(),
  status: z.enum(CAMERA_STATUSES).default("OFFLINE"),
  isDemo: z.boolean().default(false),
});

export const updateCameraSchema = createCameraSchema.partial();

export const idParamSchema = z.object({ id: z.string().min(1) });

export type CreateCameraInput = z.infer<typeof createCameraSchema>;
export type UpdateCameraInput = z.infer<typeof updateCameraSchema>;
