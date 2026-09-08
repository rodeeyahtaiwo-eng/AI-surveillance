import nodemailer, { type Transporter } from "nodemailer";
import { env } from "../../config/env";
import { logger } from "../../utils/logger";
import type { NotificationPayload, NotificationProvider, NotificationResult } from "./provider";

/**
 * Phase 2AO Stage 1 — real email delivery via Gmail SMTP. NOT wired into the threat
 * engine yet (threatEngine.service.ts still hardcodes channel: "LOG" — see Stage 2).
 * This exists standalone so it can be proven to actually send real mail before
 * anything real depends on it.
 *
 * Requires a Gmail App Password (myaccount.google.com/apppasswords), not the real
 * account password — Gmail rejects plain-password SMTP auth outright for any account
 * with 2-Step Verification on, and Google has been steadily deprecating "less secure
 * app" password auth entirely, so an App Password is the only real Stage-1 path here.
 */
export class EmailNotificationProvider implements NotificationProvider {
  readonly channel = "EMAIL" as const;
  private transporter: Transporter;
  private user: string;

  constructor(user: string, pass: string) {
    this.user = user;
    this.transporter = nodemailer.createTransport({
      host: "smtp.gmail.com",
      port: 587,
      secure: false, // false for STARTTLS on 587 (true would mean implicit TLS on 465)
      auth: { user, pass },
    });
  }

  async send(payload: NotificationPayload): Promise<NotificationResult> {
    try {
      await this.transporter.sendMail({
        // Display name only -- Gmail SMTP requires the actual address to match the
        // authenticated account (this.user), it just renders as "AI Surveillance" in
        // the recipient's inbox instead of the bare address.
        from: `"AI Surveillance" <${this.user}>`,
        to: payload.recipient,
        subject: payload.subject,
        text: payload.message,
      });
      return { ok: true };
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      logger.warn(`EmailNotificationProvider failed to send: ${message}`);
      return { ok: false, error: message };
    }
  }
}

/** Returns a real provider only when both SMTP credentials are configured — null
 * otherwise, so notification/index.ts can leave "EMAIL" unregistered rather than
 * constructing a provider doomed to fail on every send. */
export function createEmailProviderIfConfigured(): EmailNotificationProvider | null {
  if (!env.SMTP_USER || !env.SMTP_PASS) return null;
  return new EmailNotificationProvider(env.SMTP_USER, env.SMTP_PASS);
}
