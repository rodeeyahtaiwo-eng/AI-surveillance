import fs from "fs";
import path from "path";
import type { Request, Response } from "express";
import multer from "multer";
import { env } from "../config/env";
import { asyncHandler } from "../middleware/errorHandler";
import { AppError } from "../middleware/errorHandler";
import * as videoUploadService from "../services/videoUpload.service";

const uploadDir = path.resolve(env.VIDEO_UPLOAD_DIR);
fs.mkdirSync(uploadDir, { recursive: true });

const storage = multer.diskStorage({
  destination: (_req, _file, cb) => cb(null, uploadDir),
  filename: (_req, file, cb) => {
    // Never trust the original filename for the on-disk name (path traversal, weird
    // characters) — keep it only as VideoUpload.originalName for display.
    const ext = path.extname(file.originalname).toLowerCase();
    cb(null, `${Date.now()}-${Math.random().toString(36).slice(2)}${ext}`);
  },
});

export const uploadVideoMiddleware = multer({
  storage,
  limits: { fileSize: env.VIDEO_UPLOAD_MAX_MB * 1024 * 1024 },
  fileFilter: (_req, file, cb) => {
    if (!videoUploadService.isAllowedVideoFile(file.originalname, file.mimetype)) {
      cb(new AppError(400, "Only video files are accepted (.mp4, .mov, .avi, .mkv, .webm).", "INVALID_FILE_TYPE"));
      return;
    }
    cb(null, true);
  },
}).single("video");

export const postVideoUpload = asyncHandler(async (req: Request, res: Response) => {
  if (!req.file) throw new AppError(400, "No video file provided (field name must be \"video\").", "NO_FILE");
  const upload = await videoUploadService.startVideoUpload(req.params.id, req.file);
  res.status(202).json({ upload });
});

export const getVideoUploadStatus = asyncHandler(async (req: Request, res: Response) => {
  const upload = await videoUploadService.getVideoUpload(req.params.id, req.params.uploadId);
  res.json({ upload });
});
