import request from "supertest";
import { createApp } from "../src/app";
import { prisma } from "../src/lib/prisma";
import { createTestAdmin, resetDb } from "./helpers";

const app = createApp();

describe("Authentication", () => {
  beforeEach(resetDb);
  afterAll(async () => prisma.$disconnect());

  it("rejects login with wrong password", async () => {
    const { email } = await createTestAdmin();
    const res = await request(app).post("/api/auth/login").send({ email, password: "wrong" });
    expect(res.status).toBe(401);
  });

  it("logs in with correct credentials and returns a JWT + user", async () => {
    const { email, password } = await createTestAdmin();
    const res = await request(app).post("/api/auth/login").send({ email, password });
    expect(res.status).toBe(200);
    expect(res.body.token).toEqual(expect.any(String));
    expect(res.body.user.email).toBe(email);
    expect(res.body.user).not.toHaveProperty("passwordHash");
  });

  it("rejects malformed login payloads with 400", async () => {
    const res = await request(app).post("/api/auth/login").send({ email: "not-an-email" });
    expect(res.status).toBe(400);
    expect(res.body.error).toBe("Validation failed");
  });

  it("rejects protected routes without a token", async () => {
    const res = await request(app).get("/api/auth/me");
    expect(res.status).toBe(401);
  });

  it("returns the current user for a valid token", async () => {
    const { email, password } = await createTestAdmin();
    const login = await request(app).post("/api/auth/login").send({ email, password });
    const res = await request(app).get("/api/auth/me").set("Authorization", `Bearer ${login.body.token}`);
    expect(res.status).toBe(200);
    expect(res.body.user.email).toBe(email);
  });

  it("rejects a tampered token", async () => {
    const res = await request(app).get("/api/auth/me").set("Authorization", "Bearer not-a-real-token");
    expect(res.status).toBe(401);
  });
});
