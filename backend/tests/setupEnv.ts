import { TEST_DATABASE_URL } from "./testEnv";

// Runs before every test file is loaded, so src/config/env.ts sees valid values when
// modules under test import it.
process.env.NODE_ENV = "test";
process.env.DATABASE_URL = TEST_DATABASE_URL;
process.env.JWT_SECRET = "test-only-secret-not-for-prod-1234567890";
process.env.INGEST_API_KEY = "test-only-ingest-key-not-for-prod-1234567890";
process.env.CORS_ORIGIN = "http://localhost:3000";
process.env.AI_SERVICE_URL = "http://localhost:8000";
