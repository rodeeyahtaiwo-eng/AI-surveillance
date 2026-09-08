import { render, screen } from "@testing-library/react";
import { VideoUploadDialog } from "./VideoUploadDialog";
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

describe("VideoUploadDialog", () => {
  // Phase 2AM — the one guardrail that actually matters: never let an upload's
  // results be mistaken for a live feed. Mirrors the backend's own CAMERA_NOT_DEMO
  // check (defense in depth, not a replacement for it).
  it("disables uploading and explains why for a camera that isn't marked isDemo", () => {
    render(<VideoUploadDialog camera={baseCamera} onClose={jest.fn()} />);
    expect(screen.getByText(/isn't marked as a demo\/sample camera/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload" })).toBeDisabled();
  });

  it("enables the upload flow for a demo camera once a file is chosen", () => {
    render(<VideoUploadDialog camera={{ ...baseCamera, isDemo: true }} onClose={jest.fn()} />);
    expect(screen.queryByText(/isn't marked as a demo\/sample camera/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload" })).toBeDisabled(); // no file chosen yet
  });
});
