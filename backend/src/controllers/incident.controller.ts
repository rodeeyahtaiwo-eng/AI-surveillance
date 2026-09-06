import type { Request, Response } from "express";
import { asyncHandler } from "../middleware/errorHandler";
import * as incidentService from "../services/incident.service";

export const getIncidents = asyncHandler(async (req: Request, res: Response) => {
  const incidents = await incidentService.listIncidents(req.query as never);
  res.json({ incidents });
});

export const getIncident = asyncHandler(async (req: Request, res: Response) => {
  const incident = await incidentService.getIncident(req.params.id);
  res.json({ incident });
});

export const patchIncident = asyncHandler(async (req: Request, res: Response) => {
  const incident = await incidentService.updateIncident(req.params.id, req.body.reviewStatus);
  res.json({ incident });
});
