import type { Request, Response } from "express";
import { asyncHandler } from "../middleware/errorHandler";
import * as inferenceService from "../services/inference.service";

export const postDetections = asyncHandler(async (req: Request, res: Response) => {
  const detections = await inferenceService.ingestDetections(req.body);
  res.status(201).json({ detections });
});

export const postAction = asyncHandler(async (req: Request, res: Response) => {
  const result = await inferenceService.ingestAction(req.body);
  res.status(201).json(result);
});
