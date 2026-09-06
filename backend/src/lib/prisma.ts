import { PrismaClient } from "@prisma/client";

/**
 * Single shared PrismaClient instance. In dev with `tsx watch`, module reloads can
 * otherwise create many clients and exhaust connections — cache on `global` to avoid it.
 */
declare global {
  // eslint-disable-next-line no-var
  var __prisma: PrismaClient | undefined;
}

export const prisma =
  global.__prisma ??
  new PrismaClient({
    log: process.env.NODE_ENV === "development" ? ["warn", "error"] : ["error"],
  });

if (process.env.NODE_ENV !== "production") {
  global.__prisma = prisma;
}
