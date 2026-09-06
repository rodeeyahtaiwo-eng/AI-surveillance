import { prisma } from "../src/lib/prisma";
import { hashPassword } from "../src/utils/password";

/** Deletes all rows in FK-safe order — call in beforeEach so tests don't leak state. */
export async function resetDb() {
  await prisma.notification.deleteMany();
  await prisma.alert.deleteMany();
  await prisma.incident.deleteMany();
  await prisma.action.deleteMany();
  await prisma.detection.deleteMany();
  await prisma.videoSegment.deleteMany();
  await prisma.systemEvent.deleteMany();
  await prisma.camera.deleteMany();
  await prisma.user.deleteMany();
}

export async function createTestAdmin(overrides?: { email?: string; password?: string }) {
  const email = overrides?.email ?? "admin@test.local";
  const password = overrides?.password ?? "TestPassword123!";
  const user = await prisma.user.create({
    data: {
      email,
      name: "Test Admin",
      role: "ADMIN",
      passwordHash: await hashPassword(password),
    },
  });
  return { user, email, password };
}
