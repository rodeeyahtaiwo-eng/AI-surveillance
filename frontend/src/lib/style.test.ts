import {
  severityStyles,
  cameraStatusStyles,
  formatTime,
  formatRelativeTime,
  isAlertStale,
  ALERT_STALENESS_SECONDS,
  isDetectionStale,
  DETECTION_STALENESS_SECONDS,
  extractTemporalContext,
} from "./style";

describe("severityStyles", () => {
  it("has an entry for every severity level", () => {
    expect(Object.keys(severityStyles).sort()).toEqual(["CRITICAL", "HIGH", "LOW", "MEDIUM"]);
  });
});

describe("cameraStatusStyles", () => {
  it("labels ONLINE as LIVE", () => {
    expect(cameraStatusStyles.ONLINE.label).toBe("LIVE");
  });
  it("labels OFFLINE distinctly from ONLINE", () => {
    expect(cameraStatusStyles.OFFLINE.label).not.toBe(cameraStatusStyles.ONLINE.label);
  });
});

describe("formatTime", () => {
  it("formats an ISO timestamp as a time string", () => {
    const result = formatTime("2026-01-01T14:32:18.000Z");
    expect(typeof result).toBe("string");
    expect(result.length).toBeGreaterThan(0);
  });
});

// Option E — staleness-aware Threat Assessment display. `now` is always passed
// explicitly here so these tests are deterministic, not dependent on the real clock.
describe("formatRelativeTime", () => {
  const now = new Date("2026-01-01T00:10:00.000Z");

  it("renders a just-created timestamp as 'just now'", () => {
    expect(formatRelativeTime("2026-01-01T00:09:55.000Z", now)).toBe("just now");
  });

  it("renders seconds-scale age in seconds", () => {
    expect(formatRelativeTime("2026-01-01T00:09:30.000Z", now)).toBe("30s ago");
  });

  it("renders minutes-scale age in minutes, singular for exactly one minute", () => {
    expect(formatRelativeTime("2026-01-01T00:09:00.000Z", now)).toBe("1 minute ago");
    expect(formatRelativeTime("2026-01-01T00:02:00.000Z", now)).toBe("8 minutes ago");
  });

  it("renders hours-scale age in hours", () => {
    const laterNow = new Date("2026-01-01T05:00:00.000Z");
    expect(formatRelativeTime("2026-01-01T00:10:00.000Z", laterNow)).toBe("4 hours ago");
  });

  it("never returns a negative age for a clock-skewed future timestamp", () => {
    const result = formatRelativeTime("2026-01-01T00:20:00.000Z", now);
    expect(result).not.toMatch(/^-/);
  });
});

describe("isAlertStale", () => {
  const now = new Date("2026-01-01T00:10:00.000Z");

  it("is not stale immediately after creation", () => {
    expect(isAlertStale(now.toISOString(), now)).toBe(false);
  });

  it("is not stale right at the boundary", () => {
    const createdAt = new Date(now.getTime() - ALERT_STALENESS_SECONDS * 1000).toISOString();
    expect(isAlertStale(createdAt, now)).toBe(false);
  });

  it("is stale just past the boundary", () => {
    const createdAt = new Date(now.getTime() - (ALERT_STALENESS_SECONDS + 1) * 1000).toISOString();
    expect(isAlertStale(createdAt, now)).toBe(true);
  });

  it("is clearly stale for an alert from an hour ago", () => {
    const createdAt = new Date(now.getTime() - 60 * 60 * 1000).toISOString();
    expect(isAlertStale(createdAt, now)).toBe(true);
  });
});

// Phase 2P — fixes a real bug (docs/phase2o-live-system-audit.md): a one-frame false
// positive used to stay in the "Objects detected" panel with no time-based expiry.
describe("isDetectionStale", () => {
  const now = new Date("2026-01-01T00:10:00.000Z");

  it("is not stale immediately after the frame was captured", () => {
    expect(isDetectionStale(now.toISOString(), now)).toBe(false);
  });

  it("is not stale right at the boundary", () => {
    const frameTimestamp = new Date(now.getTime() - DETECTION_STALENESS_SECONDS * 1000).toISOString();
    expect(isDetectionStale(frameTimestamp, now)).toBe(false);
  });

  it("is stale just past the boundary", () => {
    const frameTimestamp = new Date(now.getTime() - (DETECTION_STALENESS_SECONDS + 1) * 1000).toISOString();
    expect(isDetectionStale(frameTimestamp, now)).toBe(true);
  });

  it("uses a materially shorter window than alert staleness — detections should age out much faster than alerts", () => {
    expect(DETECTION_STALENESS_SECONDS).toBeLessThan(ALERT_STALENESS_SECONDS);
  });
});

// Phase 2AJ — surfaces the existing Phase 2T temporal prediction from a real
// ai-service rationale string. Pure text extraction, not a re-derivation.
describe("extractTemporalContext", () => {
  it("extracts the real Phase 2T sentence verbatim, from a real ai-service rationale", () => {
    const rationale =
      "base risk for 'standing' = 0.05 = 0.05. Temporal context: current action is " +
      "'standing'; model predicts 'standing' next (confidence 1.00, based on 6 prior " +
      "observations for this camera).";
    expect(extractTemporalContext(rationale)).toBe(
      "current action is 'standing'; model predicts 'standing' next (confidence 1.00, " +
        "based on 6 prior observations for this camera)."
    );
  });

  it("returns null when the rationale has no temporal context (e.g. cold start, no prior observations yet)", () => {
    expect(extractTemporalContext("base risk for 'standing' = 0.05 = 0.05.")).toBeNull();
  });

  it("returns null when there is no rationale at all (pre-migration historical row)", () => {
    expect(extractTemporalContext(null)).toBeNull();
    expect(extractTemporalContext(undefined)).toBeNull();
    expect(extractTemporalContext("")).toBeNull();
  });
});
