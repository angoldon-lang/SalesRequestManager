import { PublicClientApplication } from "@azure/msal-browser";

export type AuthMode = "local" | "entra" | "dev";
/** Impostata all'avvio da GET /auth/config: local = utente/password, entra = Microsoft, dev = nessun login. */
export let mode: AuthMode = "local";

const TOKEN_KEY = "srm_token";
const clientId = import.meta.env.VITE_AZ_CLIENT_ID as string | undefined;
const tenantId = import.meta.env.VITE_AZ_TENANT_ID as string | undefined;
const scopes = clientId ? [`api://${clientId}/access_as_user`] : [];
let msal: PublicClientApplication | null = null;

export async function initAuth(): Promise<boolean> {
  try {
    mode = (await (await fetch("/api/v1/auth/config")).json()).mode;
  } catch {
    mode = "local";
  }
  if (mode !== "entra") return true;
  if (!clientId) throw new Error("Server in modalità Microsoft Entra ma VITE_AZ_CLIENT_ID non è impostato nel build");
  msal = new PublicClientApplication({
    auth: { clientId, authority: `https://login.microsoftonline.com/${tenantId}`, redirectUri: window.location.origin },
    cache: { cacheLocation: "sessionStorage" },
  });
  await msal.initialize();
  const res = await msal.handleRedirectPromise();
  if (res?.account) msal.setActiveAccount(res.account);
  const acc = msal.getActiveAccount() ?? msal.getAllAccounts()[0];
  if (!acc) {
    await msal.loginRedirect({ scopes });
    return false;
  }
  msal.setActiveAccount(acc);
  return true;
}

export const devMode = () => mode === "dev";

export function setToken(t: string | null) {
  try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch { /* storage non disponibile */ }
}

export async function getToken(): Promise<string | null> {
  if (mode === "local") {
    try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
  }
  if (mode === "entra" && msal) {
    const account = msal.getActiveAccount()!;
    try {
      return (await msal.acquireTokenSilent({ scopes, account })).accessToken;
    } catch {
      await msal.acquireTokenRedirect({ scopes, account });
    }
  }
  return null;
}

export function logout() {
  if (mode === "entra") { msal?.logoutRedirect(); return; }
  setToken(null);
  location.assign("/");
}
