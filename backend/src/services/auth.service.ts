import { prisma } from "../lib/prisma";
import { AppError } from "../middleware/errorHandler";
import { signAuthToken } from "../utils/jwt";
import { verifyPassword } from "../utils/password";
import type { LoginInput } from "../schemas/auth.schema";

export async function login({ email, password }: LoginInput) {
  const user = await prisma.user.findUnique({ where: { email } });
  if (!user) {
    throw new AppError(401, "Invalid email or password", "INVALID_CREDENTIALS");
  }

  const valid = await verifyPassword(password, user.passwordHash);
  if (!valid) {
    throw new AppError(401, "Invalid email or password", "INVALID_CREDENTIALS");
  }

  const token = signAuthToken({ sub: user.id, email: user.email, role: user.role });
  return {
    token,
    user: { id: user.id, email: user.email, name: user.name, role: user.role },
  };
}

export async function getCurrentUser(userId: string) {
  const user = await prisma.user.findUnique({ where: { id: userId } });
  if (!user) throw new AppError(404, "User not found", "NOT_FOUND");
  return { id: user.id, email: user.email, name: user.name, role: user.role };
}
