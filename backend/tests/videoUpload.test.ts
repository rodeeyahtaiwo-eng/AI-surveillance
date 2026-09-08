import { EventEmitter } from "events";
import fs from "fs";
import path from "path";
import request from "supertest";
import { createApp } from "../src/app";
import { prisma } from "../src/lib/prisma";
import { createTestAdmin, resetDb } from "./helpers";

// Phase 2AM — never spawns a real Python process in tests: this is a fake ChildProcess
// good enough for videoUpload.service.ts's own event listeners (stdout/stderr/exit).
// The REAL spawn call (against the real run_camera.py CLI) is exercised manually, live,
// against the real ai-service/backend — see the phase report for that end-to-end run.
let lastSpawnArgs: unknown[] = [];
let exitCode = 0;
// Phase 2AN — when true (the default, used by every pre-existing test), the fake
// process "exits" on the next tick, same as before. The concurrency test below sets
// this false so it can assert a second upload is rejected WHILE the first is still
// genuinely in flight, then resolve it manually.
let autoExit = true;
let spawnedChildren: (EventEmitter & { stdout: EventEmitter; stderr: EventEmitter })[] = [];
jest.mock("child_process", () => ({
  ...jest.requireActual("child_process"),
  spawn: (...args: unknown[]) => {
    lastSpawnArgs = args;
    const child = new EventEmitter() as EventEmitter & { stdout: EventEmitter; stderr: EventEmitter };
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    spawnedChildren.push(child);
    if (autoExit) process.nextTick(() => child.emit("exit", exitCode));
    return child;
  },
}));

const app = createApp();

async function authHeader() {
  const { email, password } = await createTestAdmin();
  const login = await request(app).post("/api/auth/login").send({ email, password });
  return `Bearer ${login.body.token}`;
}

async function createCamera(auth: string, overrides: Record<string, unknown> = {}) {
  const res = await request(app)
    .post("/api/cameras")
    .set("Authorization", auth)
    .send({ name: "Test Camera", location: "Test", streamUrl: "demo://sample.mp4", isDemo: true, ...overrides });
  return res.body.camera.id as string;
}

const uploadedFiles: string[] = [];

async function pollUntilTerminal(auth: string, cameraId: string, uploadId: string, tries = 20): Promise<any> {
  for (let i = 0; i < tries; i++) {
    const res = await request(app)
      .get(`/api/cameras/${cameraId}/uploads/${uploadId}`)
      .set("Authorization", auth);
    if (res.body.upload.status === "DONE" || res.body.upload.status === "FAILED") {
      // The VideoUpload row reaching a terminal status is the last thing the test
      // itself depends on, but runProcessingJob() also restores the camera's own
      // status and logs a completion line just after that same DB write — give those
      // last, un-awaited trailing statements a moment to settle so a later test's
      // teardown doesn't log after Jest considers the suite done.
      await new Promise((r) => setTimeout(r, 50));
      return res.body.upload;
    }
    await new Promise((r) => setTimeout(r, 10));
  }
  throw new Error("Upload never reached a terminal status");
}

describe("Video upload (Phase 2AM)", () => {
  beforeEach(() => {
    exitCode = 0;
    autoExit = true;
    spawnedChildren = [];
    return resetDb();
  });
  afterAll(async () => {
    await prisma.$disconnect();
    for (const f of uploadedFiles) {
      try {
        fs.unlinkSync(f);
      } catch {
        /* already gone */
      }
    }
  });

  it("rejects unauthenticated upload requests", async () => {
    const res = await request(app).post("/api/cameras/whatever/upload");
    expect(res.status).toBe(401);
  });

  it("rejects uploading to a camera that isn't marked isDemo", async () => {
    const auth = await authHeader();
    const cameraId = await createCamera(auth, { isDemo: false });

    const res = await request(app)
      .post(`/api/cameras/${cameraId}/upload`)
      .set("Authorization", auth)
      .attach("video", Buffer.from("fake video bytes"), "clip.mp4");

    expect(res.status).toBe(400);
    expect(res.body.code).toBe("CAMERA_NOT_DEMO");
  });

  it("rejects a non-video file", async () => {
    const auth = await authHeader();
    const cameraId = await createCamera(auth);

    const res = await request(app)
      .post(`/api/cameras/${cameraId}/upload`)
      .set("Authorization", auth)
      .attach("video", Buffer.from("not a video"), "notes.txt");

    expect(res.status).toBe(400);
    expect(res.body.code).toBe("INVALID_FILE_TYPE");
  });

  it("rejects a missing camera", async () => {
    const auth = await authHeader();
    const res = await request(app)
      .post("/api/cameras/does-not-exist/upload")
      .set("Authorization", auth)
      .attach("video", Buffer.from("fake video bytes"), "clip.mp4");
    expect(res.status).toBe(404);
  });

  it("accepts a real upload to a demo camera, runs the background job, and reaches DONE", async () => {
    const auth = await authHeader();
    const cameraId = await createCamera(auth);

    const create = await request(app)
      .post(`/api/cameras/${cameraId}/upload`)
      .set("Authorization", auth)
      .attach("video", Buffer.from("fake video bytes"), "clip.mp4");

    expect(create.status).toBe(202);
    expect(create.body.upload.status).toBe("PENDING");
    expect(create.body.upload.originalName).toBe("clip.mp4");
    uploadedFiles.push(create.body.upload.filePath);

    const finalUpload = await pollUntilTerminal(auth, cameraId, create.body.upload.id);
    expect(finalUpload.status).toBe("DONE");

    // Confirms the EXISTING run_camera.py CLI was invoked (reused, not reimplemented),
    // with --no-loop so a one-shot job actually terminates.
    const [, spawnArgs] = lastSpawnArgs as [string, string[]];
    expect(spawnArgs).toEqual(
      expect.arrayContaining(["-m", "src.run_camera", "--camera-id", cameraId, "--source", "file", "--no-loop"])
    );

    // The camera's status should be restored to its pre-upload value, not left on
    // "PROCESSING" forever.
    const cameraAfter = await request(app).get(`/api/cameras/${cameraId}`).set("Authorization", auth);
    expect(cameraAfter.body.camera.status).toBe("OFFLINE");
  });

  it("marks the upload FAILED and the camera ERROR when the processing job exits non-zero", async () => {
    exitCode = 1;
    const auth = await authHeader();
    const cameraId = await createCamera(auth);

    const create = await request(app)
      .post(`/api/cameras/${cameraId}/upload`)
      .set("Authorization", auth)
      .attach("video", Buffer.from("fake video bytes"), "clip.mp4");
    uploadedFiles.push(create.body.upload.filePath);

    const finalUpload = await pollUntilTerminal(auth, cameraId, create.body.upload.id);
    expect(finalUpload.status).toBe("FAILED");
    expect(finalUpload.error).toMatch(/exited with code 1/);

    const cameraAfter = await request(app).get(`/api/cameras/${cameraId}`).set("Authorization", auth);
    expect(cameraAfter.body.camera.status).toBe("ERROR");
  });

  it("404s an upload id that belongs to a different camera", async () => {
    const auth = await authHeader();
    const cameraId = await createCamera(auth);
    const otherCameraId = await createCamera(auth);

    const create = await request(app)
      .post(`/api/cameras/${cameraId}/upload`)
      .set("Authorization", auth)
      .attach("video", Buffer.from("fake video bytes"), "clip.mp4");
    uploadedFiles.push(create.body.upload.filePath);

    const res = await request(app)
      .get(`/api/cameras/${otherCameraId}/uploads/${create.body.upload.id}`)
      .set("Authorization", auth);
    expect(res.status).toBe(404);

    await pollUntilTerminal(auth, cameraId, create.body.upload.id); // let the background job settle
  });

  // Phase 2AN — CONFIRMED, real, live corruption before this fix: two run_camera.py
  // processes both targeting the same camera_id both appended into ai-service's single
  // shared per-camera buffer, producing genuinely mixed detections/captions from two
  // unrelated videos in one Action row. This must be rejected before it can happen.
  describe("rejects a second concurrent upload to the same camera (Phase 2AN)", () => {
    it("rejects the second upload with 409 while the first is still processing, and allows a retry once it finishes", async () => {
      autoExit = false; // the first job's fake process will NOT exit until we say so
      const auth = await authHeader();
      const cameraId = await createCamera(auth);

      const first = await request(app)
        .post(`/api/cameras/${cameraId}/upload`)
        .set("Authorization", auth)
        .attach("video", Buffer.from("fake video bytes"), "first.mp4");
      uploadedFiles.push(first.body.upload.filePath);
      expect(first.status).toBe(202);
      expect(first.body.upload.status).toBe("PENDING");

      // runProcessingJob() is fired without being awaited by startVideoUpload() (by
      // design — the HTTP response must return immediately) -- give its internals a
      // moment to actually reach spawn() before this test starts asserting on it.
      await new Promise((r) => setTimeout(r, 30));

      // Confirmed genuinely still in flight before attempting the second.
      const stillRunning = await request(app)
        .get(`/api/cameras/${cameraId}/uploads/${first.body.upload.id}`)
        .set("Authorization", auth);
      expect(["PENDING", "PROCESSING"]).toContain(stillRunning.body.upload.status);

      const second = await request(app)
        .post(`/api/cameras/${cameraId}/upload`)
        .set("Authorization", auth)
        .attach("video", Buffer.from("fake video bytes"), "second.mp4");
      expect(second.status).toBe(409);
      expect(second.body.code).toBe("UPLOAD_IN_PROGRESS");

      // No second VideoUpload row was ever created for the rejected attempt.
      const count = await prisma.videoUpload.count({ where: { cameraId } });
      expect(count).toBe(1);

      // Let the first job finish, then confirm a retry succeeds.
      spawnedChildren[0]?.emit("exit", 0);
      await pollUntilTerminal(auth, cameraId, first.body.upload.id);
      autoExit = true; // the retry's own spawn should resolve normally, like every other test

      const retry = await request(app)
        .post(`/api/cameras/${cameraId}/upload`)
        .set("Authorization", auth)
        .attach("video", Buffer.from("fake video bytes"), "retry.mp4");
      uploadedFiles.push(retry.body.upload.filePath);
      expect(retry.status).toBe(202);

      await pollUntilTerminal(auth, cameraId, retry.body.upload.id);
    });

    it("does not block uploads to a DIFFERENT camera while one is in flight", async () => {
      autoExit = false;
      const auth = await authHeader();
      const cameraId = await createCamera(auth);
      const otherCameraId = await createCamera(auth);

      const first = await request(app)
        .post(`/api/cameras/${cameraId}/upload`)
        .set("Authorization", auth)
        .attach("video", Buffer.from("fake video bytes"), "first.mp4");
      uploadedFiles.push(first.body.upload.filePath);

      const onOtherCamera = await request(app)
        .post(`/api/cameras/${otherCameraId}/upload`)
        .set("Authorization", auth)
        .attach("video", Buffer.from("fake video bytes"), "other.mp4");
      uploadedFiles.push(onOtherCamera.body.upload.filePath);
      expect(onOtherCamera.status).toBe(202);

      // Give both jobs' unawaited internals a moment to actually reach spawn().
      await new Promise((r) => setTimeout(r, 30));

      // Resolve both real child processes -- the first job (still open) and the
      // second camera's job -- so nothing is left dangling into a later test.
      for (const child of spawnedChildren) child.emit("exit", 0);
      await pollUntilTerminal(auth, otherCameraId, onOtherCamera.body.upload.id);
      await pollUntilTerminal(auth, cameraId, first.body.upload.id);
    });
  });
});
