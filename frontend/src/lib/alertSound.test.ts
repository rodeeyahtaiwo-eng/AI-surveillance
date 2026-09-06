import { playAlertSound, shouldPlayAlertSound } from "./alertSound";

describe("shouldPlayAlertSound", () => {
  it("plays for CRITICAL severity", () => {
    expect(shouldPlayAlertSound({ type: "close_contact", severity: "CRITICAL" })).toBe(true);
  });

  it("plays for HIGH severity", () => {
    expect(shouldPlayAlertSound({ type: "close_contact", severity: "HIGH" })).toBe(true);
  });

  it("plays for MEDIUM severity", () => {
    expect(shouldPlayAlertSound({ type: "close_contact", severity: "MEDIUM" })).toBe(true);
  });

  it("stays silent for LOW severity", () => {
    expect(shouldPlayAlertSound({ type: "running", severity: "LOW" })).toBe(false);
  });

  it("always plays for fighting_candidate, even if severity were somehow LOW", () => {
    expect(shouldPlayAlertSound({ type: "fighting_candidate", severity: "LOW" })).toBe(true);
  });
});

describe("playAlertSound", () => {
  it("never throws when no AudioContext is available (e.g. this jsdom test environment)", () => {
    expect(() => playAlertSound()).not.toThrow();
  });

  it("calls the Web Audio API correctly when AudioContext IS available", () => {
    const start = jest.fn();
    const stop = jest.fn();
    const connectOsc = jest.fn();
    const connectGain = jest.fn();
    const setValueAtTime = jest.fn();
    const exponentialRampToValueAtTime = jest.fn();
    const close = jest.fn().mockResolvedValue(undefined);

    class FakeAudioContext {
      currentTime = 0;
      createOscillator() {
        return {
          type: "sine",
          frequency: { value: 0 },
          connect: connectOsc,
          start,
          stop,
        };
      }
      createGain() {
        return {
          gain: { setValueAtTime, exponentialRampToValueAtTime },
          connect: connectGain,
        };
      }
      close = close;
      destination = {};
    }

    const original = (window as unknown as { AudioContext?: unknown }).AudioContext;
    (window as unknown as { AudioContext: unknown }).AudioContext = FakeAudioContext;

    try {
      jest.useFakeTimers();
      playAlertSound();
      expect(start).toHaveBeenCalledTimes(2); // two beeps
      expect(stop).toHaveBeenCalledTimes(2);
      jest.advanceTimersByTime(500);
      expect(close).toHaveBeenCalled();
    } finally {
      jest.useRealTimers();
      (window as unknown as { AudioContext: unknown }).AudioContext = original;
    }
  });
});
