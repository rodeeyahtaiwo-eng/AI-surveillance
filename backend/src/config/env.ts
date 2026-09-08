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

  // Phase 2AM — uploaded-video processing (see services/videoUpload.service.ts). Spawns
  // video-processing's EXISTING, unchanged run_camera.py --source file CLI as a child
  // process; these two paths just tell the backend where that sibling project and its
  // own venv Python interpreter live on this same machine (this whole platform assumes
  // a single-machine dev/demo deployment, same as AI_SERVICE_URL/BACKEND_URL elsewhere).
  VIDEO_PROCESSING_DIR: z.string().default("../video-processing"),
  VIDEO_PROCESSING_PYTHON: z.string().default("../video-processing/venv/Scripts/python.exe"),
  // Saved uploads live outside the repo's tracked files (see .gitignore's existing
  // "backend/uploads/" entry — anticipated before this phase built anything).
  VIDEO_UPLOAD_DIR: z.string().default("./uploads"),
  VIDEO_UPLOAD_MAX_MB: z.coerce.number().int().positive().default(250),

  // Phase 2AO Stage 1 — real EMAIL notification provider (see
  // services/notification/emailProvider.ts). Optional/undefined by default: the LOG
  // provider (already the only one ever actually selected — see
  // threatEngine.service.ts's hardcoded channel: "LOG", untouched this stage) keeps
  // working with zero config either way. Gmail SMTP requires an App Password here, not
  // your real account password (see .env.example for how to generate one).
  SMTP_USER: z.string().optional(),
  SMTP_PASS: z.string().optional(),
  NOTIFY_EMAIL_TO: z.string().email().optional(),

  // Phase 2AP Stage 1 — Resend (HTTPS API, port 443) as an alternative to SMTP-based
  // EmailNotificationProvider above. Built because the presentation venue's network
  // blocked outbound SMTP on port 587 entirely (see the live-incident diagnosis in the
  // phase report: every send failed with ENETUNREACH) — Resend's API rides on normal
  // HTTPS, which is far less likely to be blocked anywhere SMTP is. Standalone/unwired
  // for now (see scripts/testSendResendEmail.ts) — not registered in notification/
  // index.ts's providers map yet, and threatEngine.service.ts is untouched this stage.
  // RESEND_FROM_EMAIL defaults to Resend's own sandbox sender, which works with zero
  // domain setup but (per Resend's docs) can only deliver to the email address the
  // Resend account itself was signed up with, until a real sending domain is verified.
  RESEND_API_KEY: z.string().optional(),
  RESEND_FROM_EMAIL: z.string().email().default("onboarding@resend.dev"),
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
