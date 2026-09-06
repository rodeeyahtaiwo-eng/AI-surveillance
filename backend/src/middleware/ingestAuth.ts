import type { NextFunction, Request, Response } from "express";
import { env } from "../config/env";
import { AppError } from "./errorHandler";

/**
 * Guards the internal ingestion endpoint (ai-service/video-processing → backend) with a
 * shared secret instead of a user JWT. This is service-to-service auth, never exposed to
 * the frontend/browser.
 */
export function requireIngestKey(req: Request, _res: Response, next: NextFunction) {
  const key = req.headers["x-ingest-key"];
  if (key !== env.INGEST_API_KEY) {
    throw new AppError(401, "Invalid or missing ingest key", "UNAUTHENTICATED");
  }
  next();
}
