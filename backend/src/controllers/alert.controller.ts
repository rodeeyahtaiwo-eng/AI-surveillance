import type { Request, Response } from "express";
import { asyncHandler } from "../middleware/errorHandler";
import * as alertService from "../services/alert.service";

export const getAlerts = asyncHandler(async (req: Request, res: Response) => {
  const alerts = await alertService.listAlerts(req.query as never);
  res.json({ alerts });
});

export const getAlert = asyncHandler(async (req: Request, res: Response) => {
  const alert = await alertService.getAlert(req.params.id);
  res.json({ alert });
});

export const patchAlertStatus = asyncHandler(async (req: Request, res: Response) => {
  const alert = await alertService.updateAlertStatus(req.params.id, req.body.status);
  res.json({ alert });
});
