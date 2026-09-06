import type { Request, Response } from "express";
import { asyncHandler } from "../middleware/errorHandler";
import * as cameraService from "../services/camera.service";

export const getCameras = asyncHandler(async (_req: Request, res: Response) => {
  const cameras = await cameraService.listCameras();
  res.json({ cameras });
});

export const getCamera = asyncHandler(async (req: Request, res: Response) => {
  const camera = await cameraService.getCamera(req.params.id);
  res.json({ camera });
});

export const postCamera = asyncHandler(async (req: Request, res: Response) => {
  const camera = await cameraService.createCamera(req.body);
  res.status(201).json({ camera });
});

export const putCamera = asyncHandler(async (req: Request, res: Response) => {
  const camera = await cameraService.updateCamera(req.params.id, req.body);
  res.json({ camera });
});

export const deleteCamera = asyncHandler(async (req: Request, res: Response) => {
  await cameraService.deleteCamera(req.params.id);
  res.status(204).send();
});
