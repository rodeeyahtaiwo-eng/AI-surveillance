import { execSync } from "child_process";
import fs from "fs";
import path from "path";
import { TEST_DATABASE_URL } from "./testEnv";

/**
 * Runs once before the whole test run: resets the SQLite test database file and pushes
 * the current Prisma schema to it, so tests always run against an up-to-date, empty DB.
 */
export default async function globalSetup() {
  const dbPath = path.resolve(__dirname, "test.db");
  if (fs.existsSync(dbPath)) fs.unlinkSync(dbPath);

  execSync("npx prisma db push --schema=../database/schema.prisma --skip-generate --accept-data-loss", {
    cwd: path.resolve(__dirname, ".."),
    env: { ...process.env, DATABASE_URL: TEST_DATABASE_URL },
    stdio: "inherit",
  });
}
