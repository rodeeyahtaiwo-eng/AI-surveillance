import { spawn } from "child_process";
import path from "path";
import { env } from "../config/env";
import { prisma } from "../lib/prisma";
import { AppError } from "../middleware/errorHandler";
import { logger } from "../utils/logger";

/**
 * Phase 2AM — triggers video-processing's EXISTING, unchanged `run_camera.py --source
 * file` CLI (see video-processing/src/sources/file_source.py's FileSource) against an
 * uploaded file, so it flows through the exact real pipeline (YOLO, BLIP, action
 * recognition, RuleBasedThreatEngine, Alert/Incident creation) a live camera uses — no
 * new detection/scoring logic here, only a trigger + a job-status record the frontend
 * can poll. Runs as a real child process, in the background: the HTTP request that
 * kicks this off returns immediately (see controllers/videoUpload.controller.ts).
 */

const MULTER_EXTENSION_ALLOWLIST = [".mp4", ".mov", ".avi", ".mkv", ".webm"];

export function isAllowedVideoFile(originalName: string, mimetype: string): boolean {
  const ext = path.extname(originalName).toLowerCase();
  return MULTER_EXTENSION_ALLOWLIST.includes(ext) || mimetype.startsWith("video/");
}

export async function startVideoUpload(cameraId: string, file: Express.Multer.File) {
  const camera = await prisma.camera.findUnique({ where: { id: cameraId } });
  if (!camera) throw new AppError(404, "Camera not found", "NOT_FOUND");

  // The one guardrail that actually matters here: Action.mode/Alert.mode are set by
  // which ai-service ADAPTER produced a row (real YOLO/BLIP, demo heuristic/rule
  // engine) — identical whether the frame came from a live camera or an uploaded file,
  // since that distinction never crosses the wire to ai-service at all (see the
  // current-state audit). Camera.isDemo is the one real "this isn't a live feed"
  // signal in this system (FileSource's own docstring: "Always tag cameras using this
  // source as demo/isDemo"). Requiring it here — rather than silently flipping it —
  // means an upload can never quietly change a real live camera's identity, and its
  // results can never be mistaken for a genuinely live feed.
  if (!camera.isDemo) {
    throw new AppError(
      400,
      "This camera isn't marked as a demo/sample camera. To keep uploaded-video " +
        "results from ever being mistaken for a live feed, video can only be " +
        "processed against a camera with isDemo=true — mark this camera as demo " +
        "(Cameras page) or choose/create a demo camera.",
      "CAMERA_NOT_DEMO"
    );
  }

  // Phase 2AN — CONFIRMED, real, live corruption before this check existed: two
  // run_camera.py processes both targeting the same camera_id both append into
  // ai-service's single shared per-camera CameraWindow (keyed only by camera_id, with
  // no concept of "which upload" a frame came from) -- real evidence showed grounded
  // detections and captions genuinely mixing two unrelated videos' content into one
  // Action row (e.g. "a man ... on the sidewalk. Grounded detections: bowl, car,
  // person." -- "bowl" belonged to a different, concurrently-processing video
  // entirely). This check is the fix: refuse a second upload for a camera that
  // already has one in flight, rather than trying to reconcile mixed results after
  // the fact. NOTE: this is a check-then-create, not a single atomic operation --  a
  // genuine simultaneous-millisecond race between two requests could in principle
  // still both pass it before either row exists. Accepted for this dev/demo-scale
  // fix; a DB-level uniqueness constraint would close that gap if it ever mattered.
  const inFlight = await prisma.videoUpload.findFirst({
    where: { cameraId, status: { in: ["PENDING", "PROCESSING"] } },
  });
  if (inFlight) {
    throw new AppError(
      409,
      "This camera already has a video processing — wait for it to finish before " +
        "uploading another.",
      "UPLOAD_IN_PROGRESS"
    );
  }

  const upload = await prisma.videoUpload.create({
    data: {
      cameraId,
      filePath: file.path,
      originalName: file.originalname,
      status: "PENDING",
    },
  });

  // Deliberately not awaited — the job runs in the background; the caller (the HTTP
  // request that just saved the file) returns immediately with the PENDING record, and
  // the frontend polls GET .../uploads/:id for status. Failures inside the job update
  // the record itself (status=FAILED, error=...); this .catch() only guards against a
  // truly unexpected error escaping runProcessingJob's own try/catch, so it can never
  // crash the server or produce an unhandled rejection warning.
  runProcessingJob(upload.id, camera.id, camera.status, file.path).catch((err) => {
    logger.error("Unexpected error running video-upload processing job", {
      uploadId: upload.id,
      error: err instanceof Error ? err.message : String(err),
    });
  });

  return upload;
}

async function runProcessingJob(
  uploadId: string,
  cameraId: string,
  originalCameraStatus: string,
  filePath: string
): Promise<void> {
  await prisma.videoUpload.update({ where: { id: uploadId }, data: { status: "PROCESSING" } });
  // Reuses the camera's existing "PROCESSING" status value (already defined in
  // CAMERA_STATUSES, already has its own badge style) rather than inventing a new one.
  await prisma.camera.update({ where: { id: cameraId }, data: { status: "PROCESSING" } });

  const pythonPath = path.resolve(env.VIDEO_PROCESSING_PYTHON);
  const cwd = path.resolve(env.VIDEO_PROCESSING_DIR);

  try {
    await new Promise<void>((resolve, reject) => {
      // Exactly video-processing's own documented CLI (README.md / docs/demo.md),
      // plus --no-loop so a one-shot upload job actually terminates instead of
      // FileSource's normal (correct, for a live demo loop) infinite replay.
      const child = spawn(
        pythonPath,
        ["-m", "src.run_camera", "--camera-id", cameraId, "--source", "file", "--path", filePath, "--no-loop"],
        { cwd }
      );

      let stderrTail = "";
      child.stdout?.on("data", (chunk: Buffer) => {
        logger.info(`[video-upload ${uploadId}] ${chunk.toString().trim()}`);
      });
      child.stderr?.on("data", (chunk: Buffer) => {
        const text = chunk.toString();
        stderrTail = (stderrTail + text).slice(-4000);
        logger.warn(`[video-upload ${uploadId}] ${text.trim()}`);
      });

      child.on("error", reject);
      child.on("exit", (code) => {
        if (code === 0) resolve();
        else reject(new Error(`run_camera.py exited with code ${code}${stderrTail ? `: ${stderrTail}` : ""}`));
      });
    });

    await prisma.videoUpload.update({ where: { id: uploadId }, data: { status: "DONE" } });
    await prisma.camera.update({ where: { id: cameraId }, data: { status: originalCameraStatus } });
    logger.info(`Video upload processing complete: ${uploadId}`);
  } catch (err) {
    const message = (err instanceof Error ? err.message : String(err)).slice(0, 1000);
    await prisma.videoUpload.update({ where: { id: uploadId }, data: { status: "FAILED", error: message } });
    await prisma.camera.update({ where: { id: cameraId }, data: { status: "ERROR" } });
    logger.error(`Video upload processing failed: ${uploadId}: ${message}`);
  }
}

export async function getVideoUpload(cameraId: string, uploadId: string) {
  const upload = await prisma.videoUpload.findUnique({ where: { id: uploadId } });
  if (!upload || upload.cameraId !== cameraId) throw new AppError(404, "Upload not found", "NOT_FOUND");
  return upload;
}
