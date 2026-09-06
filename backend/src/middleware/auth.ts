import type { NextFunction, Request, Response } from "express";
import { verifyAuthToken, type AuthTokenPayload } from "../utils/jwt";
import { AppError } from "./errorHandler";

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace Express {
    interface Request {
      user?: AuthTokenPayload;
    }
  }
}

/** Requires a valid `Authorization: Bearer <token>` header; attaches req.user. */
export function requireAuth(req: Request, _res: Response, next: NextFunction) {
  const header = req.headers.authorization;
  if (!header?.startsWith("Bearer ")) {
    throw new AppError(401, "Missing or malformed Authorization header", "UNAUTHENTICATED");
  }
  const token = header.slice("Bearer ".length);
  try {
    req.user = verifyAuthToken(token);
  } catch {
    throw new AppError(401, "Invalid or expired token", "UNAUTHENTICATED");
  }
  next();
}

/** Restricts a route to specific roles. Use after requireAuth. */
export function requireRole(...roles: string[]) {
  return (req: Request, _res: Response, next: NextFunction) => {
    if (!req.user || !roles.includes(req.user.role)) {
      throw new AppError(403, "Insufficient permissions", "FORBIDDEN");
    }
    next();
  };
}
