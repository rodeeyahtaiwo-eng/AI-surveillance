import { Router } from "express";
import { requireAuth } from "../middleware/auth";
import { validate } from "../middleware/validate";
import { idParamSchema } from "../schemas/camera.schema";
import { listIncidentsQuerySchema, updateIncidentSchema } from "../schemas/incident.schema";
import { getIncident, getIncidents, patchIncident } from "../controllers/incident.controller";

const router = Router();
router.use(requireAuth);

router.get("/", validate({ query: listIncidentsQuerySchema }), getIncidents);
router.get("/:id", validate({ params: idParamSchema }), getIncident);
router.patch(
  "/:id",
  validate({ params: idParamSchema, body: updateIncidentSchema }),
  patchIncident
);

export default router;
