import { Router } from "express";
import rateLimit from "express-rate-limit";
import { requireAuth } from "../middleware/auth";
import { validate } from "../middleware/validate";
import { loginSchema } from "../schemas/auth.schema";
import { getMe, postLogin, postLogout } from "../controllers/auth.controller";

const router = Router();

// Slow down credential-stuffing/brute-force attempts against login.
const loginLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  limit: 20,
  standardHeaders: true,
  legacyHeaders: false,
});

router.post("/login", loginLimiter, validate({ body: loginSchema }), postLogin);
router.post("/logout", requireAuth, postLogout);
router.get("/me", requireAuth, getMe);

export default router;
