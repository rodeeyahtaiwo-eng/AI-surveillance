import http from "http";
import { createApp } from "./app";
import { env } from "./config/env";
import { initWebSocket } from "./websocket";
import { logger } from "./utils/logger";
import { prisma } from "./lib/prisma";

async function main() {
  const app = createApp();
  const server = http.createServer(app);
  initWebSocket(server);

  await prisma.$connect();
  logger.info("Database connected");

  server.listen(env.PORT, () => {
    logger.info(`Backend listening on http://localhost:${env.PORT}`);
    logger.info(`WebSocket listening on ws://localhost:${env.PORT}/ws`);
  });

  const shutdown = async () => {
    logger.info("Shutting down...");
    server.close();
    await prisma.$disconnect();
    process.exit(0);
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

main().catch((err) => {
  logger.error("Fatal startup error", { message: (err as Error).message });
  process.exit(1);
});
