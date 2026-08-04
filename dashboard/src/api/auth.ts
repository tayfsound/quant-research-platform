// Sprint 22-24: minimal client-side auth — stores the JWT from /auth/login
// and exposes it as a header for the specific components that call
// now-protected endpoints (weight approval, workspace plugin management).
const TOKEN_KEY = "qrp_token";

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export function authHeaders(): Record<string, string> {
  const token = localStorage.getItem(TOKEN_KEY);
  return token ? { Authorization: `Bearer ${token}` } : {};
}
