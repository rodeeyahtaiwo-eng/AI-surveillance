import { prisma } from "../lib/prisma";
import { env } from "../config/env";
import { logger } from "../utils/logger";
import { THREAT_THRESHOLDS } from "../config/threatConfig";

async function checkAiService(): Promise<{ reachable: boolean; detail?: string }> {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 2000);
    const res = await fetch(`${env.AI_SERVICE_URL}/health`, { signal: controller.signal });
    clearTimeout(timeout);
    return { reachable: res.ok };
  } catch (err) {
    logger.warn("ai-service health check failed", { error: (err as Error).message });
    return { reachable: false, detail: "unreachable" };
  }
}

export async function getSystemStatus() {
  const [dbOk, aiService, camerasOnline, activeAlerts] = await Promise.all([
    prisma.$queryRaw`SELECT 1`.then(() => true).catch(() => false),
    checkAiService(),
    prisma.camera.count({ where: { status: "ONLINE" } }),
    prisma.alert.count({ where: { status: "NEW" } }),
  ]);

  return {
    database: { ok: dbOk },
    aiService,
    camerasOnline,
    activeAlerts,
    timestamp: new Date().toISOString(),
  };
}

/**
 * Read-only system configuration for the Settings page. Thresholds are backend config
 * (config/threatConfig.ts), not yet DB-backed/editable from the UI — see docs/api.md.
 * Deliberately does not expose secrets (JWT_SECRET, INGEST_API_KEY, DATABASE_URL).
 */
export function getSettings() {
  return {
    threatThresholds: THREAT_THRESHOLDS,
    notificationProvider: "LOG (development mode — see docs/setup.md to configure a real provider)",
    aiServiceUrl: env.AI_SERVICE_URL,
  };
}
