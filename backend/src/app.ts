import cors from "cors";
import express from "express";
import helmet from "helmet";
import morgan from "morgan";
import { env } from "./config/env";
import { errorHandler, notFoundHandler } from "./middleware/errorHandler";

import authRoutes from "./routes/auth.routes";
import cameraRoutes from "./routes/camera.routes";
import alertRoutes from "./routes/alert.routes";
import incidentRoutes from "./routes/incident.routes";
import analyticsRoutes from "./routes/analytics.routes";
import systemRoutes from "./routes/system.routes";
import inferenceRoutes from "./routes/inference.routes";

export function createApp() {
  const app = express();

  app.use(helmet());
  app.use(cors({ origin: env.CORS_ORIGIN, credentials: true }));
  app.use(express.json({ limit: "2mb" }));
  if (env.NODE_ENV !== "test") {
    app.use(morgan(env.NODE_ENV === "development" ? "dev" : "combined"));
  }

  app.get("/health", (_req, res) => res.json({ ok: true, service: "backend" }));

  app.use("/api/auth", authRoutes);
  app.use("/api/cameras", cameraRoutes);
  app.use("/api/alerts", alertRoutes);
  app.use("/api/incidents", incidentRoutes);
  app.use("/api/analytics", analyticsRoutes);
  app.use("/api/system", systemRoutes);
  app.use("/api/inference", inferenceRoutes);

  app.use(notFoundHandler);
  app.use(errorHandler);

  return app;
}
