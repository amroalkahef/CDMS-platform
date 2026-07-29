const TOKEN_KEY = "cdms_token";
const USER_KEY = "cdms_user";

export interface AuthUser {
  id: string;
  name: string;
  email: string;
  role: "editor" | "reviewer";
  created_at: string;
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getStoredUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  return raw ? (JSON.parse(raw) as AuthUser) : null;
}

export function storeSession(token: string, user: AuthUser) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

/** Redirects to the locale-aware /login page, preserving the current locale
 * prefix (e.g. /ar/login) since this runs outside next-intl's navigation
 * helpers (plain utility, not a component). */
export function redirectToLogin() {
  if (typeof window === "undefined") return;
  const locale = window.location.pathname.split("/")[1] || "en";
  window.location.assign(`/${locale}/login`);
}
