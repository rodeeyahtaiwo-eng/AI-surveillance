import { z } from "zod";

export const uploadParamSchema = z.object({ id: z.string().min(1) });
export const uploadStatusParamSchema = z.object({ id: z.string().min(1), uploadId: z.string().min(1) });
