import { prisma } from "../../lib/prisma";
import { logger } from "../../utils/logger";
import { LogNotificationProvider } from "./logProvider";
import type { NotificationProvider } from "./provider";

/**
 * Providers are selected by channel. Only LOG is wired to a real implementation today —
 * EMAIL/SMS/PUSH throw a clear "not configured" error rather than silently pretending to
 * send, until real provider credentials (SMTP, Twilio, Firebase, ...) are added via .env.
 * Swapping in a real provider means adding one class implementing NotificationProvider
 * and registering it here — no changes to callers.
 */
const providers: Record<string, NotificationProvider> = {
  LOG: new LogNotificationProvider(),
};

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
