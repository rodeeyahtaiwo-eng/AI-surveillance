import { logger } from "../../utils/logger";
import type { NotificationPayload, NotificationProvider, NotificationResult } from "./provider";

/**
 * Development notification provider: safely logs what WOULD have been sent, instead of
 * actually dispatching email/SMS. This is the default provider until real credentials
 * (SMTP, Twilio, Firebase, ...) are configured via .env — see docs/setup.md.
 */
export class LogNotificationProvider implements NotificationProvider {
  readonly channel = "LOG" as const;

  async send(payload: NotificationPayload): Promise<NotificationResult> {
    logger.info(`[DEV NOTIFICATION] to=${payload.recipient} subject="${payload.subject}"`, {
      message: payload.message,
    });
    return { ok: true };
  }
}
