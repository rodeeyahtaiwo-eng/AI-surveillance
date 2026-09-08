import { Resend } from "resend";
import { env } from "../../config/env";
import { logger } from "../../utils/logger";
import type { NotificationPayload, NotificationProvider, NotificationResult } from "./provider";

/**
 * Phase 2AP Stage 1 — real email delivery via Resend's HTTPS API (port 443), built
 * alongside the existing SMTP-based EmailNotificationProvider (not a replacement yet).
 * The presentation venue's network blocked outbound SMTP on port 587 entirely (every
 * send failed with `connect ENETUNREACH ...:587` -- see the phase report's live-incident
 * diagnosis); Resend rides on ordinary HTTPS, so it isn't subject to that specific block.
 *
 * NOT wired into the threat engine yet (threatEngine.service.ts and notification/
 * index.ts's providers map are both untouched this stage) -- this exists standalone so
 * it can be proven to actually send real mail before anything real depends on it,
 * exactly like EmailNotificationProvider's own Stage 1.
 */
export class ResendEmailProvider implements NotificationProvider {
  readonly channel = "EMAIL" as const;
  private resend: Resend;
  private fromEmail: string;

  constructor(apiKey: string, fromEmail: string) {
    this.resend = new Resend(apiKey);
    this.fromEmail = fromEmail;
  }

  async send(payload: NotificationPayload): Promise<NotificationResult> {
    try {
      // Display name only -- same "AI Surveillance" convention as
      // EmailNotificationProvider's `from`, Resend just wants it inlined into the one
      // `from` string rather than passed separately.
      const { error } = await this.resend.emails.send({
        from: `"AI Surveillance" <${this.fromEmail}>`,
        to: payload.recipient,
        subject: payload.subject,
        text: payload.message,
      });

      if (error) {
        logger.warn(`ResendEmailProvider failed to send: ${error.message}`);
        return { ok: false, error: error.message };
      }
      return { ok: true };
    } catch (err) {
      // Resend's SDK returns API-level failures as `{error}` above rather than
      // throwing (invalid_from_address, rate limits, etc.) -- this catch is for actual
      // network/transport-level failures (DNS, TLS, connection refused) reaching
      // api.resend.com itself.
      const message = err instanceof Error ? err.message : String(err);
      logger.warn(`ResendEmailProvider failed to send: ${message}`);
      return { ok: false, error: message };
    }
  }
}

/** Returns a real provider only when RESEND_API_KEY is actually configured -- null
 * otherwise, mirroring createEmailProviderIfConfigured()'s pattern. */
export function createResendEmailProviderIfConfigured(): ResendEmailProvider | null {
  if (!env.RESEND_API_KEY) return null;
  return new ResendEmailProvider(env.RESEND_API_KEY, env.RESEND_FROM_EMAIL);
}
