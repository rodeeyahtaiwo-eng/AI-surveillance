"use client";

import { useEffect, useRef, useState } from "react";
import { getToken } from "./api";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:4000/ws";

export interface RealtimeEvent<T = unknown> {
  type: string;
  payload: T;
  timestamp: string;
}

/**
 * Subscribes to the backend WebSocket event stream (see docs/api.md) and invokes
 * `onEvent` for every message. Reconnects with backoff if the connection drops, so a
 * page left open keeps receiving live detection/alert/incident events without a refresh.
 *
 * Returns `{ connected }` so pages that want to show WebSocket status (e.g. Live
 * Monitoring's System Status panel) can — existing callers that ignore the return value
 * are unaffected.
 */
export function useRealtime(onEvent: (event: RealtimeEvent) => void) {
  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const token = getToken();
    if (!token) return;

    let socket: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let closedByCleanup = false;

    function connect() {
      socket = new WebSocket(`${WS_URL}?token=${encodeURIComponent(token!)}`);

      socket.onopen = () => setConnected(true);

      socket.onmessage = (msg) => {
        try {
          const event = JSON.parse(msg.data) as RealtimeEvent;
          if (event.type !== "connected") handlerRef.current(event);
        } catch {
          // ignore malformed frames
        }
      };

      socket.onclose = () => {
        setConnected(false);
        if (!closedByCleanup) retryTimer = setTimeout(connect, 3000);
      };
    }

    connect();

    return () => {
      closedByCleanup = true;
      if (retryTimer) clearTimeout(retryTimer);
      socket?.close();
    };
  }, []);

  return { connected };
}
