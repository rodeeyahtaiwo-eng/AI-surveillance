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

export const getActionHistory = asyncHandler(async (req: Request, res: Response) => {
  const { cameraId } = req.query as unknown as { cameraId: string };
  const history = await inferenceService.getActionHistory(cameraId);
  res.status(200).json({ history });
});
