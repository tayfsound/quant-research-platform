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
// hep login ekranına düşüyordu. JWT sunucu tarafında 30 gün geçerli
// (JWT_EXPIRE_MINUTES) — süresi dolarsa ilk korumalı istek zaten 401
// döner, o zaman gerçekten yeniden login gerekir.
export function hasToken(): boolean {
  return !!localStorage.getItem(TOKEN_KEY);
}

export function authHeaders(): Record<string, string> {
  const token = localStorage.getItem(TOKEN_KEY);
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// Faz 268ag — kullanıcı isteği: "süresi dolduğunda otomatik log ekranına
// düşsün." Gerçek bulgu: token süresi dolunca her sayfa kendi ham "HTTP
// 401" hatasını gösteriyordu (bkz. Performance.tsx vb.) — kullanıcı bunu
// backend'in çökmesiyle karıştırdı. 14 view dosyasının her birindeki
// fetch çağrısını tek tek sarmalamak yerine (bu projenin "local
// çalışıyoruz, minimal kal" ilkesine ters, büyük bir refactor) window.
// fetch'i uygulama başlarken BİR kez sarmalıyoruz. SADECE Authorization
// header'ı GÖNDERİLMİŞ bir istek 401 dönerse tepki veriyoruz — login
// formunun kendi "yanlış şifre" 401'i Authorization header'ı hiç
// göndermediği için bundan etkilenmiyor, kullanıcı yanlışlıkla login
// ekranına atılıp hata mesajını kaybetmiyor.
export function installAuthExpiryHandler() {
  const originalFetch = window.fetch.bind(window);
  window.fetch = async (...args: Parameters<typeof fetch>) => {
    const res = await originalFetch(...args);
    if (res.status === 401) {
      const init = args[1] as RequestInit | undefined;
      const headers = init?.headers as Record<string, string> | undefined;
      const hadAuthHeader = !!(headers && (headers.Authorization || headers.authorization));
      if (hadAuthHeader) {
        clearToken();
        window.location.reload();
      }
    }
    return res;
  };
}
