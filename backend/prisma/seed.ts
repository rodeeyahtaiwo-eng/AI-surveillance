import "dotenv/config";
import { PrismaClient } from "@prisma/client";
import { hashPassword } from "../src/utils/password";

const prisma = new PrismaClient();

async function main() {
  const adminEmail = process.env.ADMIN_EMAIL ?? "admin@example.com";
  const adminPassword = process.env.ADMIN_PASSWORD ?? "ChangeMe123!";
  const adminName = process.env.ADMIN_NAME ?? "Default Admin";

  const admin = await prisma.user.upsert({
    where: { email: adminEmail },
    update: {},
    create: {
      email: adminEmail,
      name: adminName,
      role: "ADMIN",
      passwordHash: await hashPassword(adminPassword),
    },
  });
  console.log(`✔ Admin user ready: ${admin.email}`);

  // The current project demonstration uses exactly ONE physical webcam — see
  // docs/demo.md. The backend/schema/API remain fully multi-camera-capable; this is
  // just what gets seeded for the single-camera demo setup. Only created if no cameras
  // exist yet, so re-running seed is safe. Add more cameras anytime via the Cameras page.
  const cameraCount = await prisma.camera.count();
  if (cameraCount === 0) {
    await prisma.camera.create({
      data: {
        name: "Camera 01",
        location: "Main Monitoring Camera",
        streamUrl: "webcam://0",
        description: "Primary demonstration camera — connect via video-processing's --source webcam.",
        status: "OFFLINE",
        isDemo: false,
      },
    });
    console.log("✔ Camera seeded: Camera 01 — Main Monitoring Camera");
  }
}

main()
  .catch((err) => {
    console.error("Seed failed:", err);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
