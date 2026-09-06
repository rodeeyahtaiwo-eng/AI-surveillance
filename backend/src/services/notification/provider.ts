/**
 * Notification provider abstraction. Every channel (email, SMS, push, dev log)
 * implements this interface so NotificationService never needs to know which
 * concrete provider is wired in — see docs/architecture.md "replaceability contract".
 */
export interface NotificationPayload {
  recipient: string;
  subject: string;
  message: string;
}

export interface NotificationResult {
  ok: boolean;
  error?: string;
}

export interface NotificationProvider {
  readonly channel: "EMAIL" | "SMS" | "PUSH" | "LOG";
  send(payload: NotificationPayload): Promise<NotificationResult>;
}
