// Sign-in: Microsoft Entra ID through MSAL when configured, otherwise a local
// development sign-in (type an email that an Admin has added).
import { PublicClientApplication, InteractionRequiredAuthError } from "@azure/msal-browser";

const tenant = import.meta.env.VITE_ENTRA_TENANT_ID as string | undefined;
const clientId = import.meta.env.VITE_ENTRA_CLIENT_ID as string | undefined;
const apiClientId = import.meta.env.VITE_ENTRA_API_CLIENT_ID as string | undefined;
// login.microsoftonline.com, or login.microsoftonline.us for Azure Government / GCC High.
const authorityHost = (import.meta.env.VITE_ENTRA_AUTHORITY_HOST as string | undefined) || "login.microsoftonline.com";

export const entraEnabled = Boolean(tenant && clientId && apiClientId);
const scopes = [`api://${apiClientId}/access_as_user`];

export const msal = entraEnabled
  ? new PublicClientApplication({
      auth: {
        clientId: clientId!,
        authority: `https://${authorityHost}/${tenant}`,
        redirectUri: window.location.origin,
      },
      cache: { cacheLocation: "sessionStorage" },
    })
  : null;

const DEV_KEY = "qca-crm.devUser";

export function devUser(): string | null {
  try {
    return localStorage.getItem(DEV_KEY);
  } catch {
    return null;
  }
}

export function setDevUser(email: string | null) {
  try {
    if (email) localStorage.setItem(DEV_KEY, email);
    else localStorage.removeItem(DEV_KEY);
  } catch {
    /* storage unavailable */
  }
}

export async function signIn(): Promise<void> {
  if (!msal) return;
  await msal.loginRedirect({ scopes });
}

export async function signOut(): Promise<void> {
  if (msal) await msal.logoutRedirect();
  else setDevUser(null);
}

export async function authHeaders(): Promise<Record<string, string>> {
  if (!msal) {
    const u = devUser();
    return u ? { "X-Dev-User": u } : {};
  }
  const account = msal.getActiveAccount() ?? msal.getAllAccounts()[0];
  if (!account) throw new Error("You're signed out. Reload the page and sign in with Microsoft.");
  try {
    const r = await msal.acquireTokenSilent({ scopes, account });
    return { Authorization: `Bearer ${r.accessToken}` };
  } catch (e) {
    // Don't jump away from the page mid-click (that looked like "nothing happened"); say so instead.
    if (e instanceof InteractionRequiredAuthError)
      throw new Error("Your Microsoft sign-in has expired. Click Sign out, sign in again, and retry.");
    throw new Error(`Microsoft sign-in problem: ${(e as Error)?.message ?? e}`);
  }
}

export async function initAuth(): Promise<boolean> {
  if (!msal) return devUser() !== null;
  await msal.initialize();
  const r = await msal.handleRedirectPromise();
  if (r?.account) msal.setActiveAccount(r.account);
  return msal.getAllAccounts().length > 0;
}
