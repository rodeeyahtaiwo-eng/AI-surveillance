import { Router } from "express";
import { requireAuth } from "../middleware/auth";
import { validate } from "../middleware/validate";
import { idParamSchema } from "../schemas/camera.schema";
import { listAlertsQuerySchema, updateAlertStatusSchema } from "../schemas/alert.schema";
import { getAlert, getAlerts, patchAlertStatus } from "../controllers/alert.controller";

const router = Router();
router.use(requireAuth);

router.get("/", validate({ query: listAlertsQuerySchema }), getAlerts);
router.get("/:id", validate({ params: idParamSchema }), getAlert);
router.patch(
  "/:id",
  validate({ params: idParamSchema, body: updateAlertStatusSchema }),
  patchAlertStatus
);

export default router;
