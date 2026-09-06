import { Router } from "express";
import { requireAuth } from "../middleware/auth";
import { asyncHandler } from "../middleware/errorHandler";
import { getSettings, getSystemStatus } from "../services/system.service";

const router = Router();

router.get(
  "/status",
  requireAuth,
  asyncHandler(async (_req, res) => {
    res.json(await getSystemStatus());
  })
);

router.get(
  "/settings",
  requireAuth,
  asyncHandler(async (_req, res) => {
    res.json(getSettings());
  })
);

export default router;
