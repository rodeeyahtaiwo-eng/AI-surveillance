"use client";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:4000/api";
const TOKEN_KEY = "surveillance.token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  window.localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** Thin fetch wrapper: attaches the JWT, resolves against NEXT_PUBLIC_API_URL, and
 * throws ApiError with the backend's message on non-2xx responses. */
export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(options.headers);
  // Phase 2AM — a FormData body (e.g. video upload) must NOT get an explicit
  // Content-Type here: fetch sets multipart/form-data with the correct boundary
  // itself only when the header is left unset. This path isn't used for uploads
  // anyway (see uploadVideo(), which needs XHR for progress events), but keeping
  // apiFetch itself FormData-safe avoids a footgun for any future caller.
  if (!(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });

  if (res.status === 204) return undefined as T;

  const body = await res.json().catch(() => ({}));

  if (!res.ok) {
    throw new ApiError(res.status, body.error ?? `Request failed with status ${res.status}`);
  }

  return body as T;
}

/** Generic SWR fetcher — the `<T>` on each `useSWR<T>(...)` call site supplies the
 * actual response type, so this stays untyped (`any`) rather than fighting SWR's
 * fetcher/key generic inference across every call site. */
export const fetcher = (path: string): Promise<any> => apiFetch(path);

// Phase 2AM — dedicated upload helper, not routed through apiFetch: plain fetch has no
// reliable, broadly-supported way to report upload progress, while XMLHttpRequest's
// upload.onprogress does, and a real byte-level percentage is worth the extra code
// here over an indeterminate spinner.
export function uploadVideo(
  cameraId: string,
  file: File,
  onProgress?: (percent: number) => void
): Promise<{ upload: import("./types").VideoUpload }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_URL}/cameras/${cameraId}/upload`);
    const token = getToken();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);

    xhr.upload.onprogress = (event) => {
      if (onProgress && event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };

    xhr.onload = () => {
      let body: { error?: string; upload?: unknown } = {};
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        // non-JSON response (e.g. a proxy error page) -- fall through to the status-based message below
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body as { upload: import("./types").VideoUpload });
      } else {
        reject(new ApiError(xhr.status, body.error ?? `Upload failed with status ${xhr.status}`));
      }
    };
    xhr.onerror = () => reject(new ApiError(0, "Network error during upload"));

    const formData = new FormData();
    formData.append("video", file);
    xhr.send(formData);
  });
}

export const api = {
  get: <T>(path: string) => apiFetch<T>(path),
  post: <T>(path: string, data?: unknown) =>
    apiFetch<T>(path, { method: "POST", body: data ? JSON.stringify(data) : undefined }),
  put: <T>(path: string, data?: unknown) =>
    apiFetch<T>(path, { method: "PUT", body: data ? JSON.stringify(data) : undefined }),
  patch: <T>(path: string, data?: unknown) =>
    apiFetch<T>(path, { method: "PATCH", body: data ? JSON.stringify(data) : undefined }),
  delete: <T>(path: string) => apiFetch<T>(path, { method: "DELETE" }),
};
