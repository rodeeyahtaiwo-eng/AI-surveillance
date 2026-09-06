import type { Request, Response } from "express";
import { asyncHandler } from "../middleware/errorHandler";
import * as authService from "../services/auth.service";

export const postLogin = asyncHandler(async (req: Request, res: Response) => {
  const result = await authService.login(req.body);
  res.json(result);
});

export const getMe = asyncHandler(async (req: Request, res: Response) => {
  const user = await authService.getCurrentUser(req.user!.sub);
  res.json({ user });
});

/** Logout is stateless (JWT) — the client simply discards the token. This endpoint
 * exists so the frontend has a single, consistent place to call and so a future
 * token-blocklist can be added without changing the client contract. */
export const postLogout = asyncHandler(async (_req: Request, res: Response) => {
  res.json({ ok: true });
});
