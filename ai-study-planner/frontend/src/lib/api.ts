const BASE = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
const KEY = "asp_token";

export const tokenStore = {
  get: () => localStorage.getItem(KEY),
  set: (t: string) => localStorage.setItem(KEY, t),
  clear: () => localStorage.removeItem(KEY),
};

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}
let onUnauthorized: () => void = () => {};
export const setUnauthorizedHandler = (fn: () => void) => { onUnauthorized = fn; };

export async function api<T = unknown>(path: string, opts: { method?: string; body?: unknown; auth?: boolean } = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  const token = tokenStore.get();
  if (token && opts.auth !== false) headers.Authorization = `Bearer ${token}`;
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { method: opts.method || "GET", headers, body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined });
  } catch {
    throw new ApiError(0, "Can't reach the server. Check your connection — the backend may be waking up (free hosting sleeps), try again in ~30s.");
  }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401 && opts.auth !== false && token) onUnauthorized();
    const detail = typeof data?.detail === "string" ? data.detail : "Something went wrong. Please try again.";
    throw new ApiError(res.status, detail);
  }
  return data as T;
}
export const get = <T,>(p: string) => api<T>(p);
export const post = <T,>(p: string, body?: unknown) => api<T>(p, { method: "POST", body: body ?? {} });
export const put = <T,>(p: string, body: unknown) => api<T>(p, { method: "PUT", body });
export const del = <T,>(p: string) => api<T>(p, { method: "DELETE" });
