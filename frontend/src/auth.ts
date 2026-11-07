import { PublicClientApplication } from "@azure/msal-browser";

const clientId = import.meta.env.VITE_AZ_CLIENT_ID as string | undefined;
const tenantId = import.meta.env.VITE_AZ_TENANT_ID as string | undefined;

/** Senza client id configurato l'app gira in modalità sviluppo (backend con AUTH_DISABLED=true). */
export const devMode = !clientId;
const scopes = clientId ? [`api://${clientId}/access_as_user`] : [];

const msal = clientId
  ? new PublicClientApplication({
      auth: { clientId, authority: `https://login.microsoftonline.com/${tenantId}`, redirectUri: window.location.origin },
      cache: { cacheLocation: "sessionStorage" },
    })
  : null;

export async function initAuth(): Promise<boolean> {
  if (!msal) return true;
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

export async function getToken(): Promise<string | null> {
  if (!msal) return null;
  const account = msal.getActiveAccount()!;
  try {
    return (await msal.acquireTokenSilent({ scopes, account })).accessToken;
  } catch {
    await msal.acquireTokenRedirect({ scopes, account });
    return null;
  }
}

export function logout() {
  msal?.logoutRedirect();
}
