import { Router } from "express";
import { requireIngestKey } from "../middleware/ingestAuth";
import { validate } from "../middleware/validate";
import { ingestActionSchema, ingestDetectionsSchema } from "../schemas/inference.schema";
import { postAction, postDetections } from "../controllers/inference.controller";

/**
 * Internal ingestion API: ai-service (and video-processing) POST inference results here.
 * Guarded by a shared secret (x-ingest-key), not a user JWT — this is service-to-service,
 * never called from the browser/frontend. See docs/architecture.md.
 */
const router = Router();
router.use(requireIngestKey);

router.post("/detections", validate({ body: ingestDetectionsSchema }), postDetections);
router.post("/actions", validate({ body: ingestActionSchema }), postAction);

export default router;
