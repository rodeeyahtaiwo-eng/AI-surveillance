import "dotenv/config";
import { z } from "zod";

/**
 * All environment variables the backend depends on, validated once at startup.
 * Fail fast with a clear message rather than crashing later on `undefined`.
 */
const envSchema = z.object({
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  PORT: z.coerce.number().int().positive().default(4000),
  CORS_ORIGIN: z.string().default("http://localhost:3000"),
  DATABASE_URL: z.string().min(1, "DATABASE_URL is required"),
  JWT_SECRET: z
    .string()
    .min(16, "JWT_SECRET must be at least 16 characters — see backend/.env.example")
    .default("INSECURE-DEV-ONLY-SECRET-change-me-before-deploying"),
  JWT_EXPIRES_IN: z.string().default("8h"),
  ADMIN_EMAIL: z.string().email().default("admin@example.com"),
  ADMIN_PASSWORD: z.string().min(6).default("ChangeMe123!"),
  ADMIN_NAME: z.string().default("Default Admin"),
  INGEST_API_KEY: z
    .string()
    .min(16, "INGEST_API_KEY must be at least 16 characters — see backend/.env.example")
    .default("INSECURE-DEV-ONLY-INGEST-KEY-change-me-before-deploying"),
  AI_SERVICE_URL: z.string().default("http://localhost:8000"),
});

const INSECURE_DEFAULTS = new Set([
  "INSECURE-DEV-ONLY-SECRET-change-me-before-deploying",
  "INSECURE-DEV-ONLY-INGEST-KEY-change-me-before-deploying",
]);

function loadEnv() {
  const parsed = envSchema.safeParse(process.env);
  if (!parsed.success) {
    // eslint-disable-next-line no-console
    console.error("❌ Invalid environment configuration:");
    for (const issue of parsed.error.issues) {
      // eslint-disable-next-line no-console
      console.error(`  - ${issue.path.join(".")}: ${issue.message}`);
    }
    throw new Error("Invalid environment configuration — see backend/.env.example");
  }

  const data = parsed.data;

  if (
    data.NODE_ENV === "production" &&
    (INSECURE_DEFAULTS.has(data.JWT_SECRET) || INSECURE_DEFAULTS.has(data.INGEST_API_KEY))
  ) {
    throw new Error(
      "Refusing to start in production with insecure default JWT_SECRET/INGEST_API_KEY — " +
        "set real secrets in backend/.env (see backend/.env.example)."
    );
  }

  if (data.NODE_ENV === "development" && INSECURE_DEFAULTS.has(data.JWT_SECRET)) {
    // eslint-disable-next-line no-console
    console.warn(
      "⚠️  Using insecure default JWT_SECRET/INGEST_API_KEY — fine for local dev only. " +
        "Set real values in backend/.env before deploying."
    );
  }

  return data;
}

export const env = loadEnv();
export type Env = typeof env;
