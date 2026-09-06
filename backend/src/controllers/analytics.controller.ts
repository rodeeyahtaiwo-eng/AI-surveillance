import type { Request, Response } from "express";
import { asyncHandler } from "../middleware/errorHandler";
import * as analyticsService from "../services/analytics.service";

export const getOverview = asyncHandler(async (_req: Request, res: Response) => {
  const overview = await analyticsService.getOverview();
  res.json(overview);
});

export const getAnalytics = asyncHandler(async (req: Request, res: Response) => {
  const analytics = await analyticsService.getAnalytics(req.query as never);
  res.json(analytics);
});
