"use client";

import { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import type { Camera, CameraStatus } from "@/lib/types";

export interface CameraFormValues {
  name: string;
  location: string;
  streamUrl: string;
  description?: string;
  status: CameraStatus;
  isDemo: boolean;
}

export function CameraFormDialog({
  initial,
  onClose,
  onSubmit,
}: {
  initial?: Camera;
  onClose: () => void;
  onSubmit: (values: CameraFormValues) => Promise<void>;
}) {
  const [values, setValues] = useState<CameraFormValues>({
    name: initial?.name ?? "",
    location: initial?.location ?? "",
    streamUrl: initial?.streamUrl ?? "",
    description: initial?.description ?? "",
    status: initial?.status ?? "OFFLINE",
    isDemo: initial?.isDemo ?? false,
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await onSubmit(values);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save camera");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal title={initial ? "Edit Camera" : "Add Camera"} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <Field label="Name">
          <input
            required
            value={values.name}
            onChange={(e) => setValues({ ...values, name: e.target.value })}
            className={inputClass}
            placeholder="Camera 01"
          />
        </Field>
        <Field label="Location">
          <input
            required
            value={values.location}
            onChange={(e) => setValues({ ...values, location: e.target.value })}
            className={inputClass}
            placeholder="Main Entrance"
          />
        </Field>
        <Field label="Stream URL">
          <input
            required
            value={values.streamUrl}
            onChange={(e) => setValues({ ...values, streamUrl: e.target.value })}
            className={inputClass}
            placeholder="rtsp://user:pass@host:554/stream or demo://sample.mp4"
          />
        </Field>
        <Field label="Description">
          <textarea
            value={values.description}
            onChange={(e) => setValues({ ...values, description: e.target.value })}
            className={inputClass}
            rows={2}
          />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Status">
            <select
              value={values.status}
              onChange={(e) => setValues({ ...values, status: e.target.value as CameraStatus })}
              className={inputClass}
            >
              <option value="OFFLINE">Offline</option>
              <option value="ONLINE">Online</option>
              <option value="PROCESSING">Processing</option>
              <option value="ERROR">Error</option>
            </select>
          </Field>
          <Field label="Demo camera">
            <label className="mt-2 flex items-center gap-2 text-sm text-slate-300">
              <input
                type="checkbox"
                checked={values.isDemo}
                onChange={(e) => setValues({ ...values, isDemo: e.target.checked })}
                className="h-4 w-4 rounded border-surface-border bg-white/5"
              />
              Uses demo/uploaded footage, not a live feed
            </label>
          </Field>
        </div>

        {error && <p className="text-sm text-red-400">{error}</p>}

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={submitting}>
            {submitting ? "Saving..." : "Save"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

const inputClass =
  "w-full rounded-md border border-surface-border bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-blue-500";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-slate-400">{label}</label>
      {children}
    </div>
  );
}
