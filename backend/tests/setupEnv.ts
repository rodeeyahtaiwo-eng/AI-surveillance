import path from "node:path";
import { TEST_DATABASE_URL } from "./testEnv";

// Phase 2AO Stage 2 — src/config/env.ts runs `import "dotenv/config"` unconditionally
// on its OWN first import (which happens later than this file, e.g. when a test pulls
// in ../src/app), and by default that loads the real backend/.env from the repo root —
// meaning any real secret a developer has configured there (SMTP_USER/SMTP_PASS
// included) leaks straight into every test run. Explicitly setting individual keys to
// "" or deleting them here does NOT fix this: dotenv only skips keys that are already
// PRESENT in process.env, so `delete` makes a key look unset again and dotenv refills
// it right back in from the real .env (confirmed live — a test run using `delete` still
// resolved a real SMTP_USER/SMTP_PASS and attempted a real send, see the phase report).
// The general, robust fix is to stop dotenv from ever reading the real .env file during
// tests at all: dotenv's `dotenv/config` preloader reads DOTENV_CONFIG_PATH to decide
// which file to load, and silently no-ops if that file doesn't exist. Pointing it at a
// path that deliberately does not exist means env.ts's dotenv.config() call loads
// nothing, so every optional key (SMTP_USER, SMTP_PASS, NOTIFY_EMAIL_TO, and any future
// one) is genuinely absent/undefined in tests — exactly matching real "not configured"
// production behavior — with no per-key allowlist to keep maintaining.
process.env.DOTENV_CONFIG_PATH = path.resolve(__dirname, ".env.does-not-exist");

// Runs before every test file is loaded, so src/config/env.ts sees valid values when
// modules under test import it.
process.env.NODE_ENV = "test";
process.env.DATABASE_URL = TEST_DATABASE_URL;
process.env.JWT_SECRET = "test-only-secret-not-for-prod-1234567890";
process.env.INGEST_API_KEY = "test-only-ingest-key-not-for-prod-1234567890";
process.env.CORS_ORIGIN = "http://localhost:3000";
process.env.AI_SERVICE_URL = "http://localhost:8000";
