import { act, render, screen } from "@testing-library/react";
import { CameraHero } from "./CameraHero";
import type { Camera } from "@/lib/types";

const baseCamera: Camera = {
  id: "cam-1",
  name: "Camera 01",
  location: "Main Monitoring Camera",
  streamUrl: "webcam://0",
  status: "OFFLINE",
  isDemo: false,
  createdAt: "2026-01-01T00:00:00.000Z",
  updatedAt: "2026-01-01T00:00:00.000Z",
};

const defaultProps = {
  recentDetections: [],
  latestAction: null,
  latestAlert: null,
  aiServiceReachable: false,
  backendReachable: true,
  wsConnected: false,
};

describe("CameraHero", () => {
  it("renders the camera name and location", () => {
    render(<CameraHero camera={baseCamera} {...defaultProps} />);
    expect(screen.getByText(/Camera 01/)).toBeInTheDocument();
    expect(screen.getByText(/Main Monitoring Camera/)).toBeInTheDocument();
  });

  it("shows the honest CAMERA NOT CONNECTED empty state when offline — never a fake feed", () => {
    render(<CameraHero camera={baseCamera} {...defaultProps} />);
    expect(screen.getByText("CAMERA NOT CONNECTED")).toBeInTheDocument();
    expect(screen.getByText(/No live video stream/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Connect Camera/i })).toHaveAttribute("href", "/cameras");
  });

  it("shows the AI-active-no-preview state when the camera is ONLINE, not a fabricated video", () => {
    render(<CameraHero camera={{ ...baseCamera, status: "ONLINE" }} {...defaultProps} />);
    expect(screen.getByText(/AI analysis active — no video preview/)).toBeInTheDocument();
    expect(screen.queryByText("CAMERA NOT CONNECTED")).not.toBeInTheDocument();
  });

  it("shows a DEMO badge when the camera is flagged isDemo", () => {
    render(<CameraHero camera={{ ...baseCamera, isDemo: true }} {...defaultProps} />);
    expect(screen.getByText("DEMO")).toBeInTheDocument();
  });

  it("does not fabricate activity when nothing has been detected yet", () => {
    render(<CameraHero camera={baseCamera} {...defaultProps} />);
    expect(screen.getByText("No current detections")).toBeInTheDocument();
    expect(screen.getByText("No active alert")).toBeInTheDocument();
  });

  it("renders real detection counts when provided and fresh", () => {
    const justNow = new Date().toISOString();
    render(
      <CameraHero
        camera={baseCamera}
        {...defaultProps}
        recentDetections={[
          { id: "d1", cameraId: "cam-1", objectLabel: "person", confidence: 0.9, boundingBox: "[]", mode: "REAL", frameTimestamp: justNow, createdAt: justNow },
          { id: "d2", cameraId: "cam-1", objectLabel: "person", confidence: 0.9, boundingBox: "[]", mode: "REAL", frameTimestamp: justNow, createdAt: justNow },
        ]}
      />
    );
    expect(screen.getByText("person × 2")).toBeInTheDocument();
  });

  it("badges the Threat Assessment section DEMO when the underlying alert is simulated — never lets a demo escalation look real", () => {
    render(
      <CameraHero
        camera={baseCamera}
        {...defaultProps}
        latestAlert={{
          id: "a1",
          cameraId: "cam-1",
          type: "fighting_candidate",
          severity: "CRITICAL",
          confidence: 0.6,
          description: "Sustained aggressive contact — potential fight detected.",
          status: "NEW",
          mode: "DEMO",
          threatScore: 0.9,
          createdAt: "2026-01-01T00:00:00.000Z",
          updatedAt: "2026-01-01T00:00:00.000Z",
        }}
      />
    );
    expect(screen.getByText("DEMO")).toBeInTheDocument();
    expect(screen.getByText("CRITICAL")).toBeInTheDocument();
  });

  it("reflects real system status connectivity, not assumed-good defaults", () => {
    render(<CameraHero camera={baseCamera} {...defaultProps} aiServiceReachable={false} wsConnected={false} />);
    const unavailable = screen.getAllByText("Unavailable");
    expect(unavailable.length).toBeGreaterThan(0);
  });

  // Option E — staleness-aware Threat Assessment display. Presentation only: these
  // tests never touch the Alert record, only how CameraHero renders a given createdAt.
  describe("alert staleness (Option E)", () => {
    const alertBase = {
      id: "a1",
      cameraId: "cam-1",
      type: "fighting_candidate",
      severity: "CRITICAL" as const,
      confidence: 0.9,
      description: "Sustained aggressive contact — potential fight detected.",
      status: "NEW" as const,
      mode: "REAL" as const,
      threatScore: 0.9,
      updatedAt: "2026-01-01T00:00:00.000Z",
    };

    it("shows a fresh CRITICAL alert as a current detection, not historical", () => {
      const justNow = new Date().toISOString();
      render(
        <CameraHero
          camera={baseCamera}
          {...defaultProps}
          latestAlert={{ ...alertBase, createdAt: justNow }}
        />
      );
      expect(screen.getByText(/^Detected /)).toBeInTheDocument();
      expect(screen.queryByText(/Historical alert/)).not.toBeInTheDocument();
    });

    it("labels an old CRITICAL alert as historical, not an ongoing threat", () => {
      const longAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString(); // 1 hour ago
      render(
        <CameraHero
          camera={baseCamera}
          {...defaultProps}
          latestAlert={{ ...alertBase, createdAt: longAgo }}
        />
      );
      // Still shows the real severity — the record itself is untouched — but clearly
      // flagged as historical, not a live/ongoing threat.
      expect(screen.getByText("CRITICAL")).toBeInTheDocument();
      expect(screen.getByText(/Historical alert — no recent threat signal/)).toBeInTheDocument();
      expect(screen.getByText(/hour/)).toBeInTheDocument();
    });

    it("shows no staleness row at all when there is no alert", () => {
      render(<CameraHero camera={baseCamera} {...defaultProps} latestAlert={null} />);
      expect(screen.queryByText(/Historical alert/)).not.toBeInTheDocument();
      expect(screen.queryByText(/^Detected /)).not.toBeInTheDocument();
      expect(screen.getByText("No active alert")).toBeInTheDocument();
    });

    it("a stale alert just past the boundary is still identified as historical", () => {
      const justOverBoundary = new Date(Date.now() - 121_000).toISOString(); // > 120s
      render(
        <CameraHero
          camera={baseCamera}
          {...defaultProps}
          latestAlert={{ ...alertBase, createdAt: justOverBoundary }}
        />
      );
      expect(screen.getAllByText(/Historical alert/).length).toBeGreaterThan(0);
    });
  });

  // Phase 2P — fixes a real bug (docs/phase2o-live-system-audit.md): the "Objects
  // detected" panel used to keep the last 8 raw events with no time-based expiry, so a
  // one-frame false positive stayed visible indefinitely. See lib/style.ts
  // DETECTION_STALENESS_SECONDS (8s) for the boundary and its rationale.
  describe("detection staleness (Phase 2P)", () => {
    const detection = (overrides: Partial<import("@/lib/types").Detection> = {}) => ({
      id: "d1",
      cameraId: "cam-1",
      objectLabel: "toothbrush",
      confidence: 0.6,
      boundingBox: "[]",
      mode: "REAL" as const,
      frameTimestamp: new Date().toISOString(),
      createdAt: new Date().toISOString(),
      ...overrides,
    });

    it("shows a fresh detection", () => {
      render(<CameraHero camera={baseCamera} {...defaultProps} recentDetections={[detection()]} />);
      expect(screen.getByText("toothbrush × 1")).toBeInTheDocument();
    });

    it("does not show a detection older than the staleness window on initial render", () => {
      const longAgo = new Date(Date.now() - 30_000).toISOString(); // 30s > 8s window
      render(
        <CameraHero
          camera={baseCamera}
          {...defaultProps}
          recentDetections={[detection({ frameTimestamp: longAgo })]}
        />
      );
      expect(screen.queryByText(/toothbrush/)).not.toBeInTheDocument();
      expect(screen.getByText("No current detections")).toBeInTheDocument();
    });

    it("a detection present at mount disappears once the staleness window elapses, with no new event", () => {
      jest.useFakeTimers();
      try {
        const freshAtMount = new Date().toISOString();
        render(
          <CameraHero
            camera={baseCamera}
            {...defaultProps}
            recentDetections={[detection({ frameTimestamp: freshAtMount })]}
          />
        );
        expect(screen.getByText("toothbrush × 1")).toBeInTheDocument();

        // Advance real+fake time past the 8s staleness window; the component's own
        // 1s ticker (not a new WebSocket event) must be what causes it to disappear.
        act(() => {
          jest.advanceTimersByTime(9000);
        });

        expect(screen.queryByText(/toothbrush/)).not.toBeInTheDocument();
        expect(screen.getByText("No current detections")).toBeInTheDocument();
      } finally {
        jest.useRealTimers();
      }
    });

    it("historical database records are never shown as current — a stale detection is filtered exactly like a never-received one", () => {
      const hourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
      render(
        <CameraHero
          camera={baseCamera}
          {...defaultProps}
          recentDetections={[detection({ frameTimestamp: hourAgo, objectLabel: "cat" })]}
        />
      );
      expect(screen.queryByText(/cat/)).not.toBeInTheDocument();
    });
  });
});
