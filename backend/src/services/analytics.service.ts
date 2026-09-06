import { prisma } from "../lib/prisma";
import type { AnalyticsQuery } from "../schemas/analytics.schema";

function dateRange(query: AnalyticsQuery) {
  const where: { gte?: Date; lte?: Date } = {};
  if (query.from) where.gte = new Date(query.from);
  if (query.to) where.lte = new Date(query.to);
  return Object.keys(where).length ? where : undefined;
}

/** Powers the top-of-dashboard stat cards + recent incidents list. */
export async function getOverview() {
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);

  const [totalCameras, camerasOnline, activeAlerts, incidentsToday, recentIncidents, severityCounts] =
    await Promise.all([
      prisma.camera.count(),
      prisma.camera.count({ where: { status: "ONLINE" } }),
      prisma.alert.count({ where: { status: { in: ["NEW", "ESCALATED"] } } }),
      prisma.incident.count({ where: { createdAt: { gte: startOfToday } } }),
      prisma.incident.findMany({ orderBy: { createdAt: "desc" }, take: 5 }),
      prisma.alert.groupBy({
        by: ["severity"],
        where: { status: { in: ["NEW", "ESCALATED"] } },
        _count: { _all: true },
      }),
    ]);

  const threatLevelSummary = { LOW: 0, MEDIUM: 0, HIGH: 0, CRITICAL: 0 } as Record<string, number>;
  for (const row of severityCounts) threatLevelSummary[row.severity] = row._count._all;

  return {
    totalCameras,
    camerasOnline,
    activeAlerts,
    incidentsToday,
    threatLevelSummary,
    recentIncidents,
  };
}

/** Powers the Analytics page charts, filterable by date/camera/severity/event type. */
export async function getAnalytics(query: AnalyticsQuery) {
  const createdAt = dateRange(query);
  const alertWhere = {
    createdAt,
    cameraId: query.cameraId,
    severity: query.severity,
    type: query.eventType,
  };

  const [alerts, incidentsBySeverity, detectionCounts, cameraActivity, reviewStats] = await Promise.all([
    prisma.alert.findMany({
      where: alertWhere,
      select: { createdAt: true, severity: true },
      orderBy: { createdAt: "asc" },
    }),
    prisma.incident.groupBy({
      by: ["severity"],
      where: { createdAt, severity: query.severity },
      _count: { _all: true },
    }),
    prisma.detection.groupBy({
      by: ["objectLabel"],
      where: { frameTimestamp: createdAt, cameraId: query.cameraId },
      _count: { _all: true },
    }),
    prisma.detection.groupBy({
      by: ["cameraId"],
      where: { frameTimestamp: createdAt },
      _count: { _all: true },
    }),
    prisma.incident.groupBy({
      by: ["reviewStatus"],
      where: { createdAt },
      _count: { _all: true },
    }),
  ]);

  // Bucket alerts by calendar day for a time-series chart.
  const alertsOverTime = new Map<string, number>();
  for (const alert of alerts) {
    const day = alert.createdAt.toISOString().slice(0, 10);
    alertsOverTime.set(day, (alertsOverTime.get(day) ?? 0) + 1);
  }

  const incidentsByType = await prisma.incident.groupBy({
    by: ["eventType"],
    where: { createdAt, severity: query.severity },
    _count: { _all: true },
  });

  return {
    alertsOverTime: Array.from(alertsOverTime.entries()).map(([date, count]) => ({ date, count })),
    incidentsByType: incidentsByType.map((r) => ({ type: r.eventType, count: r._count._all })),
    incidentsBySeverity: incidentsBySeverity.map((r) => ({ severity: r.severity, count: r._count._all })),
    detectionCounts: detectionCounts.map((r) => ({ object: r.objectLabel, count: r._count._all })),
    cameraActivity: cameraActivity.map((r) => ({ cameraId: r.cameraId, count: r._count._all })),
    reviewStats: reviewStats.map((r) => ({ status: r.reviewStatus, count: r._count._all })),
  };
}
