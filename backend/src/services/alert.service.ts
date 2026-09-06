import { prisma } from "../lib/prisma";
import { AppError } from "../middleware/errorHandler";
import { broadcast } from "../websocket";
import type { ListAlertsQuery } from "../schemas/alert.schema";

export function listAlerts(query: ListAlertsQuery) {
  return prisma.alert.findMany({
    where: {
      severity: query.severity,
      status: query.status,
      cameraId: query.cameraId,
    },
    include: { camera: true },
    orderBy: { createdAt: "desc" },
    take: query.limit,
  });
}

export async function getAlert(id: string) {
  const alert = await prisma.alert.findUnique({
    where: { id },
    include: { camera: true, action: true, incident: true, notifications: true },
  });
  if (!alert) throw new AppError(404, "Alert not found", "NOT_FOUND");
  return alert;
}

export async function updateAlertStatus(id: string, status: string) {
  await getAlert(id); // 404s if missing
  const alert = await prisma.alert.update({ where: { id }, data: { status } });
  broadcast("alert.updated", alert);
  return alert;
}
