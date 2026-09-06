import { Router } from "express";
import { requireAuth } from "../middleware/auth";
import { validate } from "../middleware/validate";
import { analyticsQuerySchema } from "../schemas/analytics.schema";
import { getAnalytics, getOverview } from "../controllers/analytics.controller";

const router = Router();
router.use(requireAuth);

router.get("/overview", getOverview);
router.get("/", validate({ query: analyticsQuerySchema }), getAnalytics);

export default router;
