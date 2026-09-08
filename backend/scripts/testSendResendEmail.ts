/**
 * Phase 2AP Stage 1 — standalone test for ResendEmailProvider. NOT part of the main
 * app flow (not called from dispatchNotification/threatEngine.service.ts -- see Stage
 * 2). Uses the provider directly, so this never writes a Notification DB row against a
 * nonexistent Alert. Mirrors scripts/testSendEmail.ts (the SMTP/Gmail equivalent).
 *
 * Usage (from backend/):
 *   npx tsx scripts/testSendResendEmail.ts
 *
 * Requires RESEND_API_KEY and NOTIFY_EMAIL_TO set in backend/.env. Get an API key at
 * resend.com (Dashboard -> API Keys). RESEND_FROM_EMAIL defaults to Resend's sandbox
 * sender ("onboarding@resend.dev"), which needs no domain setup but -- per Resend's own
 * docs -- can only deliver to the email address the Resend account was signed up with,
 * until a real sending domain is verified.
 */
import { env } from "../src/config/env";
import { ResendEmailProvider } from "../src/services/notification/resendEmailProvider";

async function main() {
  if (!env.RESEND_API_KEY) {
    console.error(
      "RESEND_API_KEY is not set in backend/.env — nothing to test.\n" +
        "Sign up at resend.com, create an API key (Dashboard -> API Keys), and add it " +
        "to backend/.env."
    );
    process.exitCode = 1;
    return;
  }
  if (!env.NOTIFY_EMAIL_TO) {
    console.error("NOTIFY_EMAIL_TO is not set in backend/.env — nowhere to send the test email.");
    process.exitCode = 1;
    return;
  }

  console.log(
    `Sending a real test email via Resend (HTTPS, port 443) from ${env.RESEND_FROM_EMAIL} to ${env.NOTIFY_EMAIL_TO}...`
  );

  const provider = new ResendEmailProvider(env.RESEND_API_KEY, env.RESEND_FROM_EMAIL);
  const result = await provider.send({
    recipient: env.NOTIFY_EMAIL_TO,
    subject: "[AI Surveillance] Test email — Phase 2AP Stage 1 (Resend)",
    message:
      "This is a real, standalone test of ResendEmailProvider (Resend's HTTPS API, " +
      "port 443 — not SMTP port 587).\n\n" +
      "It was NOT sent through the threat engine or any real Alert -- this script " +
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
