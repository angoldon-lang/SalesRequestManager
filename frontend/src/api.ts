import { getToken, mode, setToken } from "./auth";

export class ApiError extends Error {
  constructor(public status: number, public detail: any) {
    super(typeof detail === "string" ? detail : detail?.message ?? `Errore ${status}`);
  }
  /** campo -> messaggio, per gli errori di validazione del backend */
  get fields(): Record<string, string> {
    return (this.detail && typeof this.detail === "object" && this.detail.fields) || {};
  }
}

export async function api<T = any>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = await getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const devUser = localStorage.getItem("srm_dev_user");
  if (devUser) headers["X-Dev-User"] = devUser;
  const res = await fetch(`/api/v1${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!res.ok) {
    let detail: any = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* corpo non JSON */ }
    // Sessione scaduta o cambio password richiesto: la UI torna alla schermata giusta
    const isLogin = path.startsWith("/auth/login") || path.startsWith("/auth/change-password");
    if (res.status === 401 && mode === "local" && !isLogin && token) {   // solo se la sessione esisteva ed è scaduta
      setToken(null);
      window.dispatchEvent(new Event("srm-session-changed"));
    }
    if (res.status === 403 && detail?.code === "PASSWORD_CHANGE_REQUIRED") window.dispatchEvent(new Event("srm-session-changed"));
    if (Array.isArray(detail)) detail = detail.map((d) => `${d.loc?.slice(1).join(".")}: ${d.msg}`).join("; ");
    throw new ApiError(res.status, detail);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export const get = <T = any>(p: string) => api<T>("GET", p);
export const post = <T = any>(p: string, b?: unknown) => api<T>("POST", p, b ?? {});
export const put = <T = any>(p: string, b?: unknown) => api<T>("PUT", p, b);
export const patch = <T = any>(p: string, b?: unknown) => api<T>("PATCH", p, b);
export const del = <T = any>(p: string) => api<T>("DELETE", p);

export function qs(params: Record<string, string | number | boolean | undefined | null>) {
  const u = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => v !== undefined && v !== null && v !== "" && u.set(k, String(v)));
  const s = u.toString();
  return s ? `?${s}` : "";
}
