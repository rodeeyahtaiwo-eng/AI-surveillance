import request from "supertest";
import { createApp } from "../src/app";
import { prisma } from "../src/lib/prisma";
import { createTestAdmin, resetDb } from "./helpers";

const app = createApp();

async function authHeader() {
  const { email, password } = await createTestAdmin();
  const login = await request(app).post("/api/auth/login").send({ email, password });
  return `Bearer ${login.body.token}`;
}

describe("Camera CRUD", () => {
  beforeEach(resetDb);
  afterAll(async () => prisma.$disconnect());

  it("rejects unauthenticated access", async () => {
    const res = await request(app).get("/api/cameras");
    expect(res.status).toBe(401);
  });

  it("creates, lists, updates, and deletes a camera", async () => {
    const auth = await authHeader();

    const create = await request(app)
      .post("/api/cameras")
      .set("Authorization", auth)
      .send({ name: "Camera 01", location: "Main Entrance", streamUrl: "rtsp://example/stream" });
    expect(create.status).toBe(201);
    expect(create.body.camera.status).toBe("OFFLINE");
    const id = create.body.camera.id;

    const list = await request(app).get("/api/cameras").set("Authorization", auth);
    expect(list.status).toBe(200);
    expect(list.body.cameras).toHaveLength(1);

    const update = await request(app)
      .put(`/api/cameras/${id}`)
      .set("Authorization", auth)
      .send({ status: "ONLINE" });
    expect(update.status).toBe(200);
    expect(update.body.camera.status).toBe("ONLINE");

    const del = await request(app).delete(`/api/cameras/${id}`).set("Authorization", auth);
    expect(del.status).toBe(204);

    const getMissing = await request(app).get(`/api/cameras/${id}`).set("Authorization", auth);
    expect(getMissing.status).toBe(404);
  });

  it("rejects creating a camera with missing required fields", async () => {
    const auth = await authHeader();
    const res = await request(app).post("/api/cameras").set("Authorization", auth).send({ name: "No location" });
    expect(res.status).toBe(400);
  });
});
