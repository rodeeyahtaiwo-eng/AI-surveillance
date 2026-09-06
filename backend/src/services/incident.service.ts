import { prisma } from "../lib/prisma";
import { AppError } from "../middleware/errorHandler";
import { broadcast } from "../websocket";
import type { ListIncidentsQuery } from "../schemas/incident.schema";

export function listIncidents(query: ListIncidentsQuery) {
  return prisma.incident.findMany({
    where: { severity: query.severity, reviewStatus: query.reviewStatus },
    orderBy: { createdAt: "desc" },
    take: query.limit,
  });
}

export async function getIncident(id: string) {
  const incident = await prisma.incident.findUnique({
    where: { id },
    include: {
      alerts: { include: { camera: true, action: true } },
      videoSegments: true,
    },
  });
  if (!incident) throw new AppError(404, "Incident not found", "NOT_FOUND");
  return incident;
}

export async function updateIncident(id: string, reviewStatus: string) {
  await getIncident(id); // 404s if missing
  const incident = await prisma.incident.update({ where: { id }, data: { reviewStatus } });
  broadcast("incident.updated", incident);
  return incident;
}
