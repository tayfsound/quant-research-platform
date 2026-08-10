// Faz 268b: kullanıcı isteği — "Dark/Light tema anahtarı Settings'e
// eklensin." index.css zaten :root[data-theme="dark"]/"light" ve
// @media (prefers-color-scheme) ile tam donanımlıydı ama hiçbir React
// kodu data-theme'i hiç set etmiyordu — yani kullanıcı sadece işletim
// sisteminin tercihine bağlıydı, manuel bir seçeneği yoktu. Bu, "system"
// (data-theme yok, OS tercihini takip et) dahil üç değerli bir tercih —
// tarayıcı yerelinde (localStorage), sunucuya kaydedilen bir uygulama
// ayarı değil (bu gerçekten kişisel bir görüntüleme tercihi).
export type ThemePreference = "light" | "dark" | "system";

const STORAGE_KEY = "theme";

export function getThemePreference(): ThemePreference {
  const stored = localStorage.getItem(STORAGE_KEY);
  return stored === "light" || stored === "dark" ? stored : "system";
}

export function applyThemePreference(pref: ThemePreference): void {
  if (pref === "system") {
    document.documentElement.removeAttribute("data-theme");
    localStorage.removeItem(STORAGE_KEY);
  } else {
    document.documentElement.setAttribute("data-theme", pref);
    localStorage.setItem(STORAGE_KEY, pref);
  }
}

// Sayfa ilk yüklenirken (main.tsx'ten, render'dan önce) çağrılır —
// böylece kullanıcının önceki seçimi ekrana "yanlış" temayla çizilip
// sonra flaş yaparak değişmez.
export function initTheme(): void {
  applyThemePreference(getThemePreference());
}
