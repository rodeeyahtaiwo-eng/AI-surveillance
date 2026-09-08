import request from "supertest";
import { createApp } from "../src/app";
import { prisma } from "../src/lib/prisma";
import { createTestAdmin, resetDb } from "./helpers";

const app = createApp();
const INGEST_KEY = process.env.INGEST_API_KEY!;

async function authHeader() {
  const { email, password } = await createTestAdmin();
  const login = await request(app).post("/api/auth/login").send({ email, password });
  return `Bearer ${login.body.token}`;
}

async function createCamera(auth: string) {
  const res = await request(app)
    .post("/api/cameras")
    .set("Authorization", auth)
    .send({ name: "Camera 01", location: "Main Entrance", streamUrl: "demo://sample.mp4", isDemo: true });
  return res.body.camera.id as string;
}

describe("Inference ingestion + Threat Engine", () => {
  beforeEach(resetDb);
  afterAll(async () => prisma.$disconnect());

  it("rejects ingestion without the ingest key", async () => {
    const res = await request(app).post("/api/inference/actions").send({});
    expect(res.status).toBe(401);
  });

  it("stores detections and broadcasts nothing crashes without a WS server attached", async () => {
    const auth = await authHeader();
    const cameraId = await createCamera(auth);

    const res = await request(app)
      .post("/api/inference/detections")
      .set("x-ingest-key", INGEST_KEY)
      .send({
        cameraId,
        mode: "DEMO",
        detections: [
          { objectLabel: "person", confidence: 0.9, boundingBox: [0, 0, 10, 10], frameTimestamp: new Date().toISOString() },
        ],
      });
    expect(res.status).toBe(201);
    expect(res.body.detections).toHaveLength(1);
  });

  it("accepts numeric-offset timestamps (e.g. Python's datetime.isoformat(), '+00:00' not 'Z')", async () => {
    const auth = await authHeader();
    const cameraId = await createCamera(auth);

    const res = await request(app)
      .post("/api/inference/detections")
      .set("x-ingest-key", INGEST_KEY)
      .send({
        cameraId,
        mode: "DEMO",
        detections: [
          { objectLabel: "person", confidence: 0.9, boundingBox: [0, 0, 10, 10], frameTimestamp: "2026-08-14T17:34:25.223456+00:00" },
        ],
      });
    expect(res.status).toBe(201);
  });

  it("does NOT create an alert for a low threat score", async () => {
    const auth = await authHeader();
    const cameraId = await createCamera(auth);

    const res = await request(app)
      .post("/api/inference/actions")
      .set("x-ingest-key", INGEST_KEY)
      .send({
        cameraId,
        mode: "DEMO",
        label: "walking",
        confidence: 0.8,
        windowStart: new Date().toISOString(),
        windowEnd: new Date().toISOString(),
        threatScore: 0.05,
      });

    expect(res.status).toBe(201);
    expect(res.body.alert).toBeUndefined();

    const alerts = await prisma.alert.findMany();
    expect(alerts).toHaveLength(0);
  });

  it("creates an Alert AND Incident for a high threat score, and the alert is reviewable via the API", async () => {
    const auth = await authHeader();
    const cameraId = await createCamera(auth);

    const ingest = await request(app)
      .post("/api/inference/actions")
      .set("x-ingest-key", INGEST_KEY)
      .send({
        cameraId,
        mode: "DEMO",
        label: "fighting",
        confidence: 0.87,
        description: "Two people in physical contact, aggressive movement detected.",
        windowStart: new Date().toISOString(),
        windowEnd: new Date().toISOString(),
        threatScore: 0.9,
      });

    expect(ingest.status).toBe(201);
    expect(ingest.body.alert.severity).toBe("CRITICAL");
    expect(ingest.body.incident).toBeTruthy();

    const alertId = ingest.body.alert.id;

    const list = await request(app).get("/api/alerts").set("Authorization", auth);
    expect(list.status).toBe(200);
    expect(list.body.alerts).toHaveLength(1);

    const patch = await request(app)
      .patch(`/api/alerts/${alertId}`)
      .set("Authorization", auth)
      .send({ status: "REVIEWED" });
    expect(patch.status).toBe(200);
    expect(patch.body.alert.status).toBe("REVIEWED");

    // Phase 2AO Stage 2 — HIGH/CRITICAL now dispatches via channel: "EMAIL" (was
    // "LOG"). tests/setupEnv.ts deliberately unsets SMTP_USER/SMTP_PASS regardless of
    // a developer's own real backend/.env, so EMAIL is never actually registered in
    // tests — this must fail gracefully via the existing "not configured" path
    // (status=FAILED), never attempt a real send. EmailNotificationProvider's own
    // send() behavior (success/failure against a real or mocked transport) is unit
    // tested separately in tests/emailProvider.test.ts; a real send is verified live,
    // manually, against the actual alert path -- see the phase report.
    const notifications = await prisma.notification.findMany({ where: { alertId } });
    expect(notifications).toHaveLength(1);
    expect(notifications[0].channel).toBe("EMAIL");
    expect(notifications[0].status).toBe("FAILED");
    expect(notifications[0].error).toMatch(/not configured/);
    // NOTIFY_EMAIL_TO is also unset in tests -- confirms the fallback recipient logic
    // in threatEngine.service.ts still resolves to something, not undefined.
    expect(notifications[0].recipient).toBe("security-team@example.com");
  });

  // Phase 2AO Stage 2 follow-up — MEDIUM now also dispatches a notification, but
  // deliberately does NOT get an Incident: the two gates were kept separate on purpose
  // (only the notification threshold moved, per explicit request), so this locks in
  // both halves of that behavior together.
  it("creates an Alert but NOT an Incident for a MEDIUM threat score, and still dispatches a notification", async () => {
    const auth = await authHeader();
    const cameraId = await createCamera(auth);

    const ingest = await request(app)
      .post("/api/inference/actions")
      .set("x-ingest-key", INGEST_KEY)
      .send({
        cameraId,
        mode: "DEMO",
        label: "close_contact",
        confidence: 0.6,
        description: "Two people in close proximity.",
        windowStart: new Date().toISOString(),
        windowEnd: new Date().toISOString(),
        threatScore: 0.5,
      });

    expect(ingest.status).toBe(201);
    expect(ingest.body.alert.severity).toBe("MEDIUM");
    expect(ingest.body.incident).toBeNull();

    const notifications = await prisma.notification.findMany({ where: { alertId: ingest.body.alert.id } });
    expect(notifications).toHaveLength(1);
    expect(notifications[0].channel).toBe("EMAIL");
    // Same test-env "not configured" path as the HIGH/CRITICAL case above -- no real
    // send is attempted here either.
    expect(notifications[0].status).toBe("FAILED");
  });

  // Phase 2AG — BLIP is a general captioner, not trained on this project's action
  // vocabulary, so a fighting_candidate alert should read a clear action tag ahead of
  // whatever caption text BLIP produced (which may not mention "fighting" at all).
  it("prepends a 'Fighting detected' tag to fighting_candidate alerts, without altering the underlying caption", async () => {
    const auth = await authHeader();
    const cameraId = await createCamera(auth);

    const ingest = await request(app)
      .post("/api/inference/actions")
      .set("x-ingest-key", INGEST_KEY)
      .send({
        cameraId,
        mode: "DEMO",
        label: "fighting_candidate",
        confidence: 0.55,
        description: "a man and woman standing in a room Grounded detections: person.",
        windowStart: new Date().toISOString(),
        windowEnd: new Date().toISOString(),
        threatScore: 0.85,
      });

    expect(ingest.status).toBe(201);
    expect(ingest.body.alert.description).toBe(
      "Fighting detected — a man and woman standing in a room Grounded detections: person."
    );
    // The underlying Action record's own description (the caption pipeline's raw
    // output) must remain completely untouched -- the tag is an Alert-only addition.
    expect(ingest.body.action.description).toBe("a man and woman standing in a room Grounded detections: person.");
  });

  it("does not tag alerts for other labels (e.g. close_contact) — scoped to fighting_candidate only", async () => {
    const auth = await authHeader();
    const cameraId = await createCamera(auth);

    const ingest = await request(app)
      .post("/api/inference/actions")
      .set("x-ingest-key", INGEST_KEY)
      .send({
        cameraId,
        mode: "DEMO",
        label: "close_contact",
        confidence: 0.5,
        description: "a man is standing in a room with a woman Grounded detections: person.",
        windowStart: new Date().toISOString(),
        windowEnd: new Date().toISOString(),
        threatScore: 0.5,
      });

    expect(ingest.status).toBe(201);
    expect(ingest.body.alert.description).toBe("a man is standing in a room with a woman Grounded detections: person.");
  });

  // Phase 2AJ — the full rationale (including a Phase 2T "Temporal context: ..."
  // sentence when present) was already sent by ai-service and validated by
  // inference.schema.ts, but previously silently dropped. This confirms it's now
  // actually stored, verbatim, and does not influence severity/alert creation.
  it("stores the full rationale string, including a Phase 2T temporal-context sentence, without it affecting severity", async () => {
    const auth = await authHeader();
    const cameraId = await createCamera(auth);
    const rationale =
      "base risk for 'standing' = 0.05 = 0.05. Temporal context: current action is " +
      "'standing'; model predicts 'standing' next (confidence 1.00, based on 6 prior " +
      "observations for this camera).";

    const ingest = await request(app)
      .post("/api/inference/actions")
      .set("x-ingest-key", INGEST_KEY)
      .send({
        cameraId,
        mode: "DEMO",
        label: "standing",
        confidence: 0.55,
        description: "a person standing calmly",
        windowStart: new Date().toISOString(),
        windowEnd: new Date().toISOString(),
        threatScore: 0.05,
        rationale,
      });

    expect(ingest.status).toBe(201);
    expect(ingest.body.action.rationale).toBe(rationale);
    expect(ingest.body.alert).toBeUndefined(); // 0.05 is below the alert threshold either way

    const stored = await prisma.action.findUnique({ where: { id: ingest.body.action.id } });
    expect(stored?.rationale).toBe(rationale);
  });

  // Phase 2AK — read-only history endpoint the Markov temporal predictor bootstraps
  // itself from (see ai-service's maybe_bootstrap_temporal_predictor()).
  describe("GET /api/inference/actions/history", () => {
    it("rejects without the ingest key", async () => {
      const res = await request(app).get("/api/inference/actions/history").query({ cameraId: "whatever" });
      expect(res.status).toBe(401);
    });

    it("returns real logged actions for a camera, oldest first, label + windowStart only", async () => {
      const auth = await authHeader();
      const cameraId = await createCamera(auth);
      const t0 = new Date();

      for (const [label, offsetSeconds] of [
        ["standing", 0],
        ["walking", 5],
        ["standing", 10],
      ] as const) {
        await request(app)
          .post("/api/inference/actions")
          .set("x-ingest-key", INGEST_KEY)
          .send({
            cameraId,
            mode: "DEMO",
            label,
            confidence: 0.5,
            windowStart: new Date(t0.getTime() + offsetSeconds * 1000).toISOString(),
            windowEnd: new Date(t0.getTime() + offsetSeconds * 1000).toISOString(),
            threatScore: 0.05,
          });
      }

      const res = await request(app)
        .get("/api/inference/actions/history")
        .set("x-ingest-key", INGEST_KEY)
        .query({ cameraId });

      expect(res.status).toBe(200);
      expect(res.body.history.map((h: { label: string }) => h.label)).toEqual(["standing", "walking", "standing"]);
      expect(Object.keys(res.body.history[0]).sort()).toEqual(["label", "windowStart"]);
    });

    it("returns an empty history for a camera with no logged actions", async () => {
      const auth = await authHeader();
      const cameraId = await createCamera(auth);

      const res = await request(app)
        .get("/api/inference/actions/history")
        .set("x-ingest-key", INGEST_KEY)
        .query({ cameraId });

      expect(res.status).toBe(200);
      expect(res.body.history).toEqual([]);
    });
  });
});
