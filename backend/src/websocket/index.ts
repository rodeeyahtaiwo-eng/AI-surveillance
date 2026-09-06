import type { Server as HttpServer } from "http";
import { WebSocket, WebSocketServer } from "ws";
import { verifyAuthToken } from "../utils/jwt";
import { logger } from "../utils/logger";

/**
 * Real-time event types broadcast to the dashboard. Keep in sync with docs/api.md.
 * The frontend never polls the REST API for these — it listens on this stream instead.
 */
export type RealtimeEventType =
  | "camera.online"
  | "camera.offline"
  | "detection.created"
  | "action.detected"
  | "alert.created"
  | "alert.updated"
  | "incident.created"
  | "incident.updated"
  | "system.error";

export interface RealtimeEvent<T = unknown> {
  type: RealtimeEventType;
  payload: T;
  timestamp: string;
}

let wss: WebSocketServer | null = null;

/** Attaches the WebSocket server to the existing HTTP server, at path /ws. */
export function initWebSocket(server: HttpServer) {
  wss = new WebSocketServer({ server, path: "/ws" });

  wss.on("connection", (socket, req) => {
    const url = new URL(req.url ?? "", "http://localhost");
    const token = url.searchParams.get("token");

    if (!token) {
      socket.close(4001, "Missing token");
      return;
    }
    try {
      verifyAuthToken(token);
    } catch {
      socket.close(4001, "Invalid token");
      return;
    }

    logger.info("WebSocket client connected");
    socket.send(JSON.stringify({ type: "connected", payload: {}, timestamp: new Date().toISOString() }));

    socket.on("close", () => logger.info("WebSocket client disconnected"));
  });

  logger.info("WebSocket server attached at /ws");
  return wss;
}

/** Broadcasts a typed event to every connected dashboard client. */
export function broadcast<T>(type: RealtimeEventType, payload: T) {
  if (!wss) return;
  const event: RealtimeEvent<T> = { type, payload, timestamp: new Date().toISOString() };
  const data = JSON.stringify(event);
  for (const client of wss.clients) {
    if (client.readyState === WebSocket.OPEN) client.send(data);
  }
}
