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

// Faz 215: kullanıcı isteği — "local çalışıyoruz, deploy etmiyoruz, her
// seferinde login yazmaya gerek yok." Token zaten localStorage'da
// kalıcıydı (tarayıcı kapansa da), ama App.tsx her sayfa yenilemesinde
// isLoggedIn'i sıfırdan false başlatıyordu — token var olsa bile kullanıcı
// hep login ekranına düşüyordu. JWT sunucu tarafında 24 saat geçerli
// (JWT_EXPIRE_MINUTES) — süresi dolarsa ilk korumalı istek zaten 401
// döner, o zaman gerçekten yeniden login gerekir.
export function hasToken(): boolean {
  return !!localStorage.getItem(TOKEN_KEY);
}

export function authHeaders(): Record<string, string> {
  const token = localStorage.getItem(TOKEN_KEY);
  return token ? { Authorization: `Bearer ${token}` } : {};
}
