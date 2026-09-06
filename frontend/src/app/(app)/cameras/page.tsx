"use client";

import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { Plus, Pencil, Trash2, Power } from "lucide-react";
import { Topbar } from "@/components/layout/Topbar";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { DemoBadge } from "@/components/ui/Badge";
import { CameraFormDialog, type CameraFormValues } from "@/components/cameras/CameraFormDialog";
import { api, fetcher } from "@/lib/api";
import { cameraStatusStyles } from "@/lib/style";
import type { Camera } from "@/lib/types";
import clsx from "clsx";


export default function CamerasPage() {
  const { data, isLoading } = useSWR<{ cameras: Camera[] }>("/cameras", fetcher);
  const { mutate } = useSWRConfig();
  const [dialogState, setDialogState] = useState<"closed" | "create" | Camera>("closed");

  const cameras = data?.cameras ?? [];

  async function handleCreate(values: CameraFormValues) {
    await api.post("/cameras", values);
    mutate("/cameras");
  }

  async function handleUpdate(id: string, values: CameraFormValues) {
    await api.put(`/cameras/${id}`, values);
    mutate("/cameras");
  }

  async function handleDelete(camera: Camera) {
    if (!confirm(`Remove camera "${camera.name}"? This cannot be undone.`)) return;
    await api.delete(`/cameras/${camera.id}`);
    mutate("/cameras");
  }

  async function handleToggle(camera: Camera) {
    await api.put(`/cameras/${camera.id}`, { status: camera.status === "ONLINE" ? "OFFLINE" : "ONLINE" });
    mutate("/cameras");
  }

  return (
    <div>
      <Topbar title="Cameras" description="Register and manage camera sources" />

      <div className="p-6">
        <div className="mb-4 flex justify-end">
          <Button variant="primary" onClick={() => setDialogState("create")}>
            <Plus className="h-4 w-4" /> Add Camera
          </Button>
        </div>

        <Card className="overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead className="bg-white/5 text-xs uppercase tracking-wide text-slate-400">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Location</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Stream URL</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border">
              {isLoading && (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-slate-500">
                    Loading...
                  </td>
                </tr>
              )}
              {!isLoading && cameras.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-slate-500">
                    No cameras yet. Click "Add Camera" to register one.
                  </td>
                </tr>
              )}
              {cameras.map((camera) => {
                const s = cameraStatusStyles[camera.status];
                return (
                  <tr key={camera.id} className="hover:bg-white/5">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-white">{camera.name}</span>
                        {camera.isDemo && <DemoBadge />}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-slate-300">{camera.location}</td>
                    <td className="px-4 py-3">
                      <span className={clsx("flex items-center gap-1.5 text-xs font-semibold", s.text)}>
                        <span className={clsx("h-1.5 w-1.5 rounded-full", s.dot)} />
                        {camera.status}
                      </span>
                    </td>
                    <td className="max-w-[240px] truncate px-4 py-3 font-mono text-xs text-slate-500">
                      {camera.streamUrl}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-1">
                        <IconButton title="Toggle online/offline" onClick={() => handleToggle(camera)}>
                          <Power className="h-4 w-4" />
                        </IconButton>
                        <IconButton title="Edit" onClick={() => setDialogState(camera)}>
                          <Pencil className="h-4 w-4" />
                        </IconButton>
                        <IconButton title="Delete" onClick={() => handleDelete(camera)} danger>
                          <Trash2 className="h-4 w-4" />
                        </IconButton>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      </div>

      {dialogState === "create" && (
        <CameraFormDialog onClose={() => setDialogState("closed")} onSubmit={handleCreate} />
      )}
      {dialogState !== "closed" && dialogState !== "create" && (
        <CameraFormDialog
          initial={dialogState}
          onClose={() => setDialogState("closed")}
          onSubmit={(values) => handleUpdate(dialogState.id, values)}
        />
      )}
    </div>
  );
}

function IconButton({
  children,
  onClick,
  title,
  danger,
}: {
  children: React.ReactNode;
  onClick: () => void;
  title: string;
  danger?: boolean;
}) {
  return (
    <button
      title={title}
      onClick={onClick}
      className={clsx(
        "rounded-md p-1.5 hover:bg-white/10",
        danger ? "text-red-400 hover:text-red-300" : "text-slate-400 hover:text-white"
      )}
    >
      {children}
    </button>
  );
}
