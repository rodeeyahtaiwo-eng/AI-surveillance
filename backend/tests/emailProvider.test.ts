import nodemailer from "nodemailer";
import { EmailNotificationProvider } from "../src/services/notification/emailProvider";

// Phase 2AO Stage 2 — unit coverage for EmailNotificationProvider.send()'s own
// success/failure branches, with nodemailer mocked so this never opens a real network
// connection. A real send is verified separately, live and manually, against the
// actual smtp.gmail.com endpoint (see backend/scripts/testSendEmail.ts and the phase
// report) — this file exists only to lock in the ok/error mapping logic itself.
jest.mock("nodemailer");

describe("EmailNotificationProvider", () => {
  afterEach(() => jest.clearAllMocks());

  it("returns ok:true when the transport sends successfully", async () => {
    const sendMail = jest.fn().mockResolvedValue({ messageId: "abc123" });
    (nodemailer.createTransport as jest.Mock).mockReturnValue({ sendMail });

    const provider = new EmailNotificationProvider("user@example.com", "app-password");
    const result = await provider.send({
      recipient: "dest@example.com",
      subject: "[CRITICAL] fighting at Camera 01",
      message: "Camera: Camera 01\nSeverity: CRITICAL (threat score 0.90)",
    });

    expect(result.ok).toBe(true);
    expect(result.error).toBeUndefined();
    expect(sendMail).toHaveBeenCalledWith(
      expect.objectContaining({
        // Display-name format -- shows as "AI Surveillance" in the inbox while still
        // sending through the actual authenticated account.
        from: '"AI Surveillance" <user@example.com>',
        to: "dest@example.com",
        subject: "[CRITICAL] fighting at Camera 01",
        text: "Camera: Camera 01\nSeverity: CRITICAL (threat score 0.90)",
      })
    );
  });

  it("returns ok:false with the underlying error message when the transport rejects", async () => {
    const sendMail = jest.fn().mockRejectedValue(new Error("535 Authentication failed"));
    (nodemailer.createTransport as jest.Mock).mockReturnValue({ sendMail });

    const provider = new EmailNotificationProvider("user@example.com", "wrong-app-password");
    const result = await provider.send({
      recipient: "dest@example.com",
      subject: "Test",
      message: "Body",
    });

    expect(result.ok).toBe(false);
    expect(result.error).toMatch(/Authentication failed/);
  });

  it("configures the transport for Gmail STARTTLS on port 587", () => {
    (nodemailer.createTransport as jest.Mock).mockReturnValue({ sendMail: jest.fn() });

    // eslint-disable-next-line no-new
    new EmailNotificationProvider("user@example.com", "app-password");

    expect(nodemailer.createTransport).toHaveBeenCalledWith(
      expect.objectContaining({
        host: "smtp.gmail.com",
        port: 587,
        secure: false,
        auth: { user: "user@example.com", pass: "app-password" },
      })
    );
  });
});
