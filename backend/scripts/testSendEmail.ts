/**
 * Phase 2AO Stage 1 — standalone test for EmailNotificationProvider. NOT part of the
 * main app flow (not called from dispatchNotification/threatEngine.service.ts, which
 * still hardcodes channel: "LOG" — see Stage 2). Uses the provider directly, so this
 * never writes a Notification DB row against a nonexistent Alert.
 *
 * Usage (from backend/):
 *   npx tsx scripts/testSendEmail.ts
 *
 * Requires SMTP_USER, SMTP_PASS (a Gmail App Password, NOT your real account
 * password), and NOTIFY_EMAIL_TO set in backend/.env — see .env.example for how to
 * generate an App Password.
 */
import { env } from "../src/config/env";
import { EmailNotificationProvider } from "../src/services/notification/emailProvider";

async function main() {
  if (!env.SMTP_USER || !env.SMTP_PASS) {
    console.error(
      "SMTP_USER/SMTP_PASS are not set in backend/.env — nothing to test.\n" +
        "See backend/.env.example's \"Email notifications\" section for how to " +
        "generate a Gmail App Password."
    );
    process.exitCode = 1;
    return;
  }
  if (!env.NOTIFY_EMAIL_TO) {
    console.error("NOTIFY_EMAIL_TO is not set in backend/.env — nowhere to send the test email.");
    process.exitCode = 1;
    return;
  }

  console.log(`Sending a real test email from ${env.SMTP_USER} to ${env.NOTIFY_EMAIL_TO}...`);

  const provider = new EmailNotificationProvider(env.SMTP_USER, env.SMTP_PASS);
  const result = await provider.send({
    recipient: env.NOTIFY_EMAIL_TO,
    subject: "[AI Surveillance] Test email — Phase 2AO Stage 1",
    message:
      "This is a real, standalone test of EmailNotificationProvider (Gmail SMTP).\n\n" +
      "It was NOT sent through the threat engine or any real Alert — this script " +
      "calls the provider directly, exactly as described in the phase report, to " +
      "confirm sending works before anything real depends on it.",
  });

  if (result.ok) {
    console.log("Sent successfully.");
  } else {
    console.error(`Failed to send: ${result.error}`);
    process.exitCode = 1;
  }
}

main();
