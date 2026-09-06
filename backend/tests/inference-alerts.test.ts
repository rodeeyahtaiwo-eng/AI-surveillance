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

    // A notification dispatch (LOG provider, dev mode) should have been recorded.
    const notifications = await prisma.notification.findMany({ where: { alertId } });
    expect(notifications).toHaveLength(1);
    expect(notifications[0].status).toBe("SENT");
  });
});
