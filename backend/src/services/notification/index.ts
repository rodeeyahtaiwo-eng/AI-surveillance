import { prisma } from "../../lib/prisma";
import { logger } from "../../utils/logger";
// Phase 2AO Stage 1 (SMTP/Gmail) -- kept, unused, in case Resend ever needs to be
// swapped back out. Not imported into `providers` below anymore; see Phase 2AP Stage 2.
// import { createEmailProviderIfConfigured } from "./emailProvider";
import { createResendEmailProviderIfConfigured } from "./resendEmailProvider";
import { LogNotificationProvider } from "./logProvider";
import type { NotificationProvider } from "./provider";

/**
 * Providers are selected by channel. LOG is always wired; EMAIL is real too, backed by
 * Resend's HTTPS API (resendEmailProvider.ts) as of Phase 2AP Stage 2 -- only registered
 * when RESEND_API_KEY is actually configured, otherwise EMAIL falls through to the same
 * "not configured" path SMS/PUSH still use.
 *
 * EMAIL was previously backed by EmailNotificationProvider (Gmail SMTP, port 587 --
 * emailProvider.ts). Switched to Resend because a real presentation venue's network
 * blocked outbound SMTP entirely (every send failed with `ENETUNREACH ...:587` -- see
 * the phase report); Resend rides on ordinary HTTPS (port 443) instead. That file is
 * untouched and still fully working (see scripts/testSendEmail.ts) -- reverting is a
 * one-line swap back to `createEmailProviderIfConfigured()` below if Resend is ever not
 * the right choice.
 *
 * Swapping in a different real provider always just means adding one class implementing
 * NotificationProvider and registering it here — no changes to callers (threatEngine
 * .service.ts asks for channel: "EMAIL" and has no idea which concrete provider answers
 * that request).
 */
const providers: Record<string, NotificationProvider> = {
  LOG: new LogNotificationProvider(),
};

const emailProvider = createResendEmailProviderIfConfigured();
if (emailProvider) providers.EMAIL = emailProvider;

export async function dispatchNotification(params: {
  alertId: string;
  channel: "EMAIL" | "SMS" | "PUSH" | "LOG";
  recipient: string;
  subject: string;
  message: string;
}) {
  const provider = providers[params.channel];

  const notification = await prisma.notification.create({
    data: {
      alertId: params.alertId,
      channel: params.channel,
      recipient: params.recipient,
      status: "PENDING",
    },
  });

  if (!provider) {
    await prisma.notification.update({
      where: { id: notification.id },
      data: { status: "FAILED", error: `Provider "${params.channel}" not configured` },
    });
    logger.warn(`Notification channel "${params.channel}" not configured — skipped`, {
      alertId: params.alertId,
    });
    return notification;
  }

  const result = await provider.send({
    recipient: params.recipient,
    subject: params.subject,
    message: params.message,
  });

  return prisma.notification.update({
    where: { id: notification.id },
    data: result.ok
      ? { status: "SENT", sentAt: new Date() }
      : { status: "FAILED", error: result.error },
  });
}
