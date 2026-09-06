import { Router } from "express";
import { requireAuth } from "../middleware/auth";
import { validate } from "../middleware/validate";
import { createCameraSchema, idParamSchema, updateCameraSchema } from "../schemas/camera.schema";
import {
  deleteCamera,
  getCamera,
  getCameras,
  postCamera,
  putCamera,
} from "../controllers/camera.controller";

const router = Router();
router.use(requireAuth);

router.get("/", getCameras);
router.post("/", validate({ body: createCameraSchema }), postCamera);
router.get("/:id", validate({ params: idParamSchema }), getCamera);
router.put("/:id", validate({ params: idParamSchema, body: updateCameraSchema }), putCamera);
router.delete("/:id", validate({ params: idParamSchema }), deleteCamera);

export default router;
