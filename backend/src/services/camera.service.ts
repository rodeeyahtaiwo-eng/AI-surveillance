import { prisma } from "../lib/prisma";
import { AppError } from "../middleware/errorHandler";
import { broadcast } from "../websocket";
import type { CreateCameraInput, UpdateCameraInput } from "../schemas/camera.schema";

export function listCameras() {
  return prisma.camera.findMany({ orderBy: { createdAt: "desc" } });
}

export async function getCamera(id: string) {
  const camera = await prisma.camera.findUnique({ where: { id } });
  if (!camera) throw new AppError(404, "Camera not found", "NOT_FOUND");
  return camera;
}

export function createCamera(data: CreateCameraInput) {
  return prisma.camera.create({ data });
}

export async function updateCamera(id: string, data: UpdateCameraInput) {
  await getCamera(id); // 404s if missing
  const camera = await prisma.camera.update({ where: { id }, data });

  if (data.status) {
    if (data.status === "ONLINE") broadcast("camera.online", { cameraId: id });
    if (data.status === "OFFLINE") broadcast("camera.offline", { cameraId: id });
  }

  return camera;
}

export async function deleteCamera(id: string) {
  await getCamera(id); // 404s if missing
  await prisma.camera.delete({ where: { id } });
}
