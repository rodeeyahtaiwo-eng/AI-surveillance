import { scoreToSeverity, THREAT_THRESHOLDS } from "../src/config/threatConfig";

describe("scoreToSeverity", () => {
  it("returns null below the LOW threshold", () => {
    expect(scoreToSeverity(THREAT_THRESHOLDS.LOW - 0.01)).toBeNull();
  });

  it.each([
    [THREAT_THRESHOLDS.LOW, "LOW"],
    [THREAT_THRESHOLDS.MEDIUM, "MEDIUM"],
    [THREAT_THRESHOLDS.HIGH, "HIGH"],
    [THREAT_THRESHOLDS.CRITICAL, "CRITICAL"],
    [1, "CRITICAL"],
  ])("maps score %f to severity %s", (score, expected) => {
    expect(scoreToSeverity(score)).toBe(expected);
  });
});
