import { Router } from "express";
import { requireAuth } from "../middleware/auth";
import { validate } from "../middleware/validate";
import { createCameraSchema, idParamSchema, updateCameraSchema } from "../schemas/camera.schema";
import { uploadParamSchema, uploadStatusParamSchema } from "../schemas/videoUpload.schema";
import {
  deleteCamera,
  getCamera,
  getCameras,
  postCamera,
  putCamera,
} from "../controllers/camera.controller";
import { getVideoUploadStatus, postVideoUpload, uploadVideoMiddleware } from "../controllers/videoUpload.controller";

const router = Router();
router.use(requireAuth);

router.get("/", getCameras);
router.post("/", validate({ body: createCameraSchema }), postCamera);
router.get("/:id", validate({ params: idParamSchema }), getCamera);
router.put("/:id", validate({ params: idParamSchema, body: updateCameraSchema }), putCamera);
router.delete("/:id", validate({ params: idParamSchema }), deleteCamera);

// Phase 2AM — upload a video file and process it through the real pipeline (see
// services/videoUpload.service.ts). validate() runs on req.params only here —
// uploadVideoMiddleware (multer) must run first to parse the multipart body at all.
router.post("/:id/upload", validate({ params: uploadParamSchema }), uploadVideoMiddleware, postVideoUpload);
router.get(
  "/:id/uploads/:uploadId",
  validate({ params: uploadStatusParamSchema }),
  getVideoUploadStatus
);

export default router;
