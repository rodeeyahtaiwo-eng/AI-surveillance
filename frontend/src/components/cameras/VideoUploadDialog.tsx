"use client";

import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Loader2, UploadCloud, XCircle } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { ApiError, api, uploadVideo } from "@/lib/api";
import type { Camera, VideoUpload } from "@/lib/types";

const POLL_INTERVAL_MS = 2000;
const ACCEPTED_EXTENSIONS = [".mp4", ".mov", ".avi", ".mkv", ".webm"];

type Phase = "idle" | "uploading" | "processing" | "done" | "failed";

/**
 * Phase 2AM — uploads a video file for `camera` and runs it through the real,
 * unchanged detection/scoring pipeline (see backend/src/services/videoUpload.service.ts
 * and video-processing/src/sources/file_source.py). This component only tracks the
 * job's own PENDING/PROCESSING/DONE/FAILED lifecycle -- the real Detections/Actions/
 * Alerts the job produces already appear in the existing Alerts/Live Monitoring pages
 * and trigger the existing alert sound, exactly like a live camera's, via the
 * pre-existing WebSocket wiring. Nothing here duplicates that.
 */
export function VideoUploadDialog({ camera, onClose }: { camera: Camera; onClose: () => void }) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, []);

  function pollStatus(uploadId: string) {
    pollTimer.current = setTimeout(async () => {
      try {
        const res = await api.get<{ upload: VideoUpload }>(`/cameras/${camera.id}/uploads/${uploadId}`);
        if (res.upload.status === "DONE") {
          setPhase("done");
        } else if (res.upload.status === "FAILED") {
          setError(res.upload.error ?? "Processing failed.");
          setPhase("failed");
        } else {
          setPhase("processing");
          pollStatus(uploadId);
        }
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Lost track of the processing job.");
        setPhase("failed");
      }
    }, POLL_INTERVAL_MS);
  }

  async function handleUpload() {
    if (!file) return;
    setError(null);
    setPhase("uploading");
    setProgress(0);
    try {
      const res = await uploadVideo(camera.id, file, setProgress);
      setPhase("processing");
      pollStatus(res.upload.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed.");
      setPhase("failed");
    }
  }

  const canUploadHere = camera.isDemo;

  return (
    <Modal title={`Upload video — ${camera.name}`} onClose={onClose}>
      {!canUploadHere && (
        <p className="mb-3 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-300">
          This camera isn&apos;t marked as a demo/sample camera. To keep uploaded-video
          results from ever being mistaken for a live feed, video can only be processed
          against a demo camera — edit this camera and enable &quot;Uses demo/uploaded
          footage&quot; first.
        </p>
      )}

      {phase === "idle" && (
        <div className="space-y-3">
          <label
            className="flex cursor-pointer flex-col items-center gap-2 rounded-md border border-dashed border-surface-border bg-white/5 px-4 py-8 text-center text-sm text-slate-400 hover:border-blue-500 hover:text-slate-200"
            aria-disabled={!canUploadHere}
          >
            <UploadCloud className="h-6 w-6" />
            {file ? file.name : "Click to choose a video file"}
            <span className="text-xs text-slate-500">MP4, MOV, AVI, MKV, or WebM</span>
            <input
              type="file"
              accept="video/*,.mp4,.mov,.avi,.mkv,.webm"
              className="hidden"
              disabled={!canUploadHere}
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>

          {file && !ACCEPTED_EXTENSIONS.some((ext) => file.name.toLowerCase().endsWith(ext)) && (
            <p className="text-sm text-red-400">
              That doesn&apos;t look like a supported video file — pick an {ACCEPTED_EXTENSIONS.join(", ")} file.
            </p>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="button" variant="primary" disabled={!canUploadHere || !file} onClick={handleUpload}>
              Upload
            </Button>
          </div>
        </div>
      )}

      {phase === "uploading" && (
        <div className="space-y-3 py-2">
          <div className="h-2 w-full overflow-hidden rounded-full bg-white/10">
            <div className="h-full bg-blue-500 transition-all" style={{ width: `${progress}%` }} />
          </div>
          <p className="text-center text-sm text-slate-300">Uploading... {progress}%</p>
        </div>
      )}

      {phase === "processing" && (
        <div className="flex flex-col items-center gap-3 py-6 text-center">
          <Loader2 className="h-6 w-6 animate-spin text-blue-400" />
          <p className="text-sm text-slate-300">
            Processing through the real detection/analysis pipeline...
          </p>
          <p className="text-xs text-slate-500">
            This runs in the background and can take longer than the video&apos;s own
            length, depending on the machine. You can close this dialog — real Alerts
            from this run will still appear on the Alerts page as they&apos;re created.
          </p>
        </div>
      )}

      {phase === "done" && (
        <div className="flex flex-col items-center gap-3 py-6 text-center">
          <CheckCircle2 className="h-8 w-8 text-severity-low" />
          <p className="text-sm text-slate-200">Processing complete.</p>
          <p className="text-xs text-slate-500">
            Any real detections/alerts from this video are already on the{" "}
            <a href="/alerts" className="text-blue-400 hover:underline">
              Alerts page
            </a>
            .
          </p>
          <Button type="button" variant="primary" onClick={onClose}>
            Close
          </Button>
        </div>
      )}

      {phase === "failed" && (
        <div className="flex flex-col items-center gap-3 py-6 text-center">
          <XCircle className="h-8 w-8 text-severity-critical" />
          <p className="text-sm text-slate-200">Processing failed.</p>
          {error && <p className="max-w-sm text-xs text-red-400">{error}</p>}
          <Button type="button" variant="ghost" onClick={onClose}>
            Close
          </Button>
        </div>
      )}
    </Modal>
  );
}
