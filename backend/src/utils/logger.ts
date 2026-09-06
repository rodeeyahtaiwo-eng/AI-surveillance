/* eslint-disable no-console */

type Level = "info" | "warn" | "error" | "debug";

function line(level: Level, message: string, meta?: unknown) {
  const ts = new Date().toISOString();
  const base = `[${ts}] [${level.toUpperCase()}] ${message}`;
  return meta !== undefined ? `${base} ${JSON.stringify(meta)}` : base;
}

/**
 * Minimal structured console logger. Kept dependency-free on purpose — swap for
 * pino/winston later without changing call sites if log volume grows.
 */
export const logger = {
  info: (message: string, meta?: unknown) => console.log(line("info", message, meta)),
  warn: (message: string, meta?: unknown) => console.warn(line("warn", message, meta)),
  error: (message: string, meta?: unknown) => console.error(line("error", message, meta)),
  debug: (message: string, meta?: unknown) => {
    if (process.env.NODE_ENV === "development") console.debug(line("debug", message, meta));
  },
};
