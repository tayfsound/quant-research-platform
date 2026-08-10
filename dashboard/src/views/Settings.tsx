import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Button, ErrorNote, Input } from "../components/ui";
import { applyThemePreference, getThemePreference, type ThemePreference } from "../lib/theme";

const THEME_LABELS: Record<ThemePreference, string> = {
  light: "Açık",
  dark: "Koyu",
  system: "Sistem",
};

type SettingsMap = Record<string, string>;

// Faz 265 — kritik bulgu: bu seçim daha önce (Faz 187) pozisyonu SÜREYE
// göre zorla kapatıyordu ("~10 dk" gibi). Faz 215'te kullanıcı isteğiyle
// ("vade dolunca kapatmak bile bile zarar etmek demek") bu tamamen
// kaldırıldı — pozisyonlar artık SADECE gerçekten stop/hedefe ulaşınca
// kapanıyor, süre hiç zorlamıyor. Ama seçim boş kalmasın diye: artık
// stop/hedef MESAFESİNİ belirliyor (dar taban = küçük mesafe = saatler
// içinde sonuçlanma eğilimi; geniş taban = büyük mesafe = günler/haftalar)
// — süre garantisi değil, eğilim.
const HORIZON_LABELS: Record<string, string> = {
  short: "Scalp (dar hedef, ~1 saatlik ATR)",
  medium: "Gün içi (orta hedef, ~4 saatlik ATR)",
  long: "Swing (geniş hedef, günlük ATR)",
};

// Faz 214: ajanların sinyal ürettiği mum aralığı — işlem vadesinden
// (trade_horizon, yukarıda) kasıtlı olarak ayrı. "4h analiz" ≠ "4h
// pozisyon tutma"; biri sinyal kalitesi, diğeri kasa/likidite kararı.
const CANDLE_TIMEFRAME_LABELS: Record<string, string> = {
  "1m": "1 dakika",
  "5m": "5 dakika",
  "15m": "15 dakika",
  "1h": "1 saat",
  "4h": "4 saat",
  "1d": "1 gün",
};

// Faz 224: kullanıcı bulgusu — "PNL de para birimi görünmüyor... her
// yerde aynı problem var." bkz. src/lib/currency.ts (paylaşılan format
// hook'u — hesaplama hep USD'de kalır, bu sadece görüntüleme tercihi).
const DISPLAY_CURRENCY_LABELS: Record<string, string> = {
  USD: "USD ($)",
  BTC: "BTC (₿)",
  TRY: "TRY (₺)",
};

export default function Settings() {
  const [settings, setSettings] = useState<SettingsMap>({});
  const [draft, setDraft] = useState<SettingsMap>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  const [resetting, setResetting] = useState(false);
  const [resetDone, setResetDone] = useState(false);

  // Faz 268k — kullanıcı bulgusu: "Minimum kâr hedefi" kutusuna ondalık
  // girilemiyordu ("0.0" yazarken sona 0 basınca her şey tek bir 0'a
  // düşüyordu). Kök neden: kutunun value'su HER render'da draft.min_
  // profit_target_pct'ten (backend'de fraction, ör. 0.02) yeniden
  // Number()*100 ile türetiliyordu — kullanıcı daha "0." yazarken bile
  // Number("0.")===0 olduğu için görüntü anında "0"a geri dönüyordu.
  // Ayrı bir görüntü-string state'i, sadece settings gerçekten yüklenince
  // (yazarken değil) senkronize ediliyor — normal React kontrollü-input
  // deseni. Fraction'a çevirme sadece Kaydet'e basınca oluyor.
  const [minProfitPctInput, setMinProfitPctInput] = useState("");
  useEffect(() => {
    setMinProfitPctInput(
      settings.min_profit_target_pct != null && settings.min_profit_target_pct !== ""
        ? String(Number(settings.min_profit_target_pct) * 100)
        : ""
    );
  }, [settings.min_profit_target_pct]);

  // Faz 268b: kullanıcı isteği — "Dark/Light tema anahtarı Settings'e
  // eklensin." Diğer ayarların aksine sunucuya kaydedilmiyor — bu
  // tarayıcıya özel bir görüntüleme tercihi, backend'in bilmesine gerek
  // yok (bkz. src/lib/theme.ts).
  const [theme, setTheme] = useState<ThemePreference>(getThemePreference());
  const chooseTheme = (pref: ThemePreference) => {
    applyThemePreference(pref);
    setTheme(pref);
  };

  // Faz 268m — kullanıcı bulgusu: max_position_size (risk_limits tablosu,
  // hash-imzalı, app_settings'ten AYRI) hiç bu sayfada yoktu — sadece bir
  // kerelik migration'la $2000'e sabitlenmişti. Kullanıcı starting_capital/
  // max_capital_pct/max_concurrent_positions'ı sonradan değiştirince (kasa
  // başına pay: starting_capital*max_capital_pct/max_concurrent_positions
  // = $25,000) bu üç ayarla senkron dışı kaldı — HER işlem SIZE_EXCEEDED
  // ile reddedilmeye başladı, üç ayarı değiştiren kullanıcı bunu asla
  // göremedi (max_position_size ayrı bir tabloda, ayrı bir sayfada bile
  // değildi). Kullanıcı kararı: kontrol tamamen kaldırılmasın (AI'ın
  // açabileceği pozisyona hâlâ bir tavan olsun), ama artık diğer üçüyle
  // AYNI sayfadan, elle yönetilebilsin.
  const [maxPositionSize, setMaxPositionSize] = useState<string>("");
  const [maxPositionSizeInput, setMaxPositionSizeInput] = useState<string>("");
  const [savingLimit, setSavingLimit] = useState(false);
  const [savedLimit, setSavedLimit] = useState(false);
  const [limitError, setLimitError] = useState<string | null>(null);

  const loadRiskLimit = () => {
    fetch("/api/v1/risk-limits/?scope=global", { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => {
        const entry = (data.limits || []).find((l: { limit_type: string }) => l.limit_type === "max_position_size");
        const value = entry ? String(entry.value) : "";
        setMaxPositionSize(value);
        setMaxPositionSizeInput(value);
      })
      .catch(() => {});
  };

  const load = () => {
    fetch("/api/v1/settings/", { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => {
        setSettings(data.settings || {});
        setDraft(data.settings || {});
      })
      .catch((e) => setError(String(e)));
    loadRiskLimit();
  };

  useEffect(load, []);

  const saveMaxPositionSize = () => {
    const value = Number(maxPositionSizeInput);
    if (!maxPositionSizeInput || Number.isNaN(value) || value <= 0) {
      setLimitError("max_position_size: pozitif bir sayı girin");
      return;
    }
    setSavingLimit(true);
    setLimitError(null);
    fetch(`/api/v1/risk-limits/max_position_size?value=${encodeURIComponent(String(value))}&scope=global`, {
      method: "POST",
      headers: authHeaders(),
    })
      .then(async (r) => {
        if (!r.ok) {
          const body = await r.json().catch(() => ({}));
          throw new Error(body.detail || `${r.status}`);
        }
        setMaxPositionSize(String(value));
        setSavedLimit(true);
        setTimeout(() => setSavedLimit(false), 1500);
      })
      .catch((e) => setLimitError(`max_position_size: ${e.message || e}`))
      .finally(() => setSavingLimit(false));
  };

  // Kasa ayarlarının GERÇEKTEN ürettiği işlem başı payı, kullanıcı henüz
  // Kaydet'e basmadan (draft'tan) canlı hesaplayıp gösteriyor — bugünkü
  // olayın (üç ayar değişti, dördüncüsü fark edilmeden senkron dışı kaldı)
  // bir daha sessizce tekrarlanmaması için.
  const computedCapitalPerTrade = (() => {
    const capital = Number(draft.starting_capital);
    const pct = Number(draft.max_capital_pct);
    const concurrent = Number(draft.max_concurrent_positions);
    if (!capital || !pct || !concurrent) return null;
    return (capital * pct) / concurrent;
  })();

  const resetToDefaults = () => {
    setResetting(true);
    setError(null);
    fetch("/api/v1/settings/reset-defaults", { method: "POST", headers: authHeaders() })
      .then(async (r) => {
        if (!r.ok) {
          const body = await r.json().catch(() => ({}));
          throw new Error(body.detail || `${r.status}`);
        }
        load();
        setResetDone(true);
        setTimeout(() => setResetDone(false), 2000);
      })
      .catch((e) => setError(`reset-defaults: ${e.message || e}`))
      .finally(() => setResetting(false));
  };

  const save = (key: string, value: string) => {
    setSaving(key);
    setError(null);
    fetch(`/api/v1/settings/${key}?value=${encodeURIComponent(value)}`, {
      method: "POST",
      headers: authHeaders(),
    })
      .then(async (r) => {
        if (!r.ok) {
          const body = await r.json().catch(() => ({}));
          throw new Error(body.detail || `${r.status}`);
        }
        setSettings((s) => ({ ...s, [key]: value }));
        setSaved(key);
        setTimeout(() => setSaved((cur) => (cur === key ? null : cur)), 1500);
      })
      .catch((e) => setError(`${key}: ${e.message || e}`))
      .finally(() => setSaving(null));
  };

  return (
    <div>
      <PageHeader
        title="Settings"
        description="Bunlar AI'ın değil, senin belirlediğin kurallar — kaç işlem aynı anda açık olabilir, kasanın max yüzde kaçı kullanılabilir, işlemler ne kadar vadeli olsun. Start/Stop ve Test/Live düğmeleri Dashboard sayfasına taşındı."
        action={
          <Button variant="secondary" onClick={resetToDefaults} disabled={resetting}>
            {resetting ? "Sıfırlanıyor…" : resetDone ? "Sıfırlandı ✓" : "Varsayılan"}
          </Button>
        }
      />

      <p className="text-xs text-ink-soft -mt-4 mb-6">
        "Varsayılanlara dön": kasa/limit/vade/mum aralığı ayarlarını, komisyona ezilmeden gerçekçi
        (~$1-5) net kâr hedefleyecek şekilde matematiksel olarak hesaplanmış değerlere sıfırlar
        (watchlist, Test/Live modu gibi tercihlerinize dokunmaz).
      </p>

      {error && <ErrorNote>{error}</ErrorNote>}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <h3 className="text-sm font-semibold text-ink mb-1">Aynı anda max açık işlem</h3>
          <p className="text-xs text-ink-soft mb-3">Live modda AI en fazla bu kadar pozisyonu aynı anda açık tutabilir.</p>
          <div className="flex gap-2">
            <Input
              type="number"
              value={draft.max_concurrent_positions ?? ""}
              onChange={(v) => setDraft((d) => ({ ...d, max_concurrent_positions: v }))}
            />
            <Button
              disabled={saving === "max_concurrent_positions"}
              onClick={() => save("max_concurrent_positions", draft.max_concurrent_positions)}
            >
              {saved === "max_concurrent_positions" ? "Kaydedildi ✓" : "Kaydet"}
            </Button>
          </div>
        </Card>

        <Card>
          <h3 className="text-sm font-semibold text-ink mb-1">Kasanın max %kaçı kullanılabilir</h3>
          <p className="text-xs text-ink-soft mb-3">0.5 = kasanın en fazla %50'si açık pozisyonlara bağlanabilir.</p>
          <div className="flex gap-2">
            <Input
              type="number"
              value={draft.max_capital_pct ?? ""}
              onChange={(v) => setDraft((d) => ({ ...d, max_capital_pct: v }))}
            />
            <Button
              disabled={saving === "max_capital_pct"}
              onClick={() => save("max_capital_pct", draft.max_capital_pct)}
            >
              {saved === "max_capital_pct" ? "Kaydedildi ✓" : "Kaydet"}
            </Button>
          </div>
        </Card>

        <Card>
          <h3 className="text-sm font-semibold text-ink mb-1">Minimum kâr hedefi (%)</h3>
          <p className="text-xs text-ink-soft mb-3">
            Yüzde olarak gir (ör. 2 = %2). Hedefin fiyatın en az bu yüzdesi kadar olması şart,
            yoksa işlem açılmaz — komisyonu karşılamayan çok küçük hedefleri eler (gerçek olay:
            hedefe ulaştı ama komisyon kârı yedi). 0 = kapalı.
          </p>
          <div className="flex gap-2">
            <Input
              type="number"
              value={minProfitPctInput}
              onChange={setMinProfitPctInput}
            />
            <Button
              disabled={saving === "min_profit_target_pct"}
              onClick={() => save(
                "min_profit_target_pct",
                minProfitPctInput === "" ? "" : String(Number(minProfitPctInput) / 100)
              )}
            >
              {saved === "min_profit_target_pct" ? "Kaydedildi ✓" : "Kaydet"}
            </Button>
          </div>
        </Card>

        <Card>
          <h3 className="text-sm font-semibold text-ink mb-1">Kasa büyüklüğü (sanal, paper trading)</h3>
          <p className="text-xs text-ink-soft mb-3">Sermaye yüzdesi hesaplaması bu değere göre yapılır.</p>
          <div className="flex gap-2">
            <Input
              type="number"
              value={draft.starting_capital ?? ""}
              onChange={(v) => setDraft((d) => ({ ...d, starting_capital: v }))}
            />
            <Button
              disabled={saving === "starting_capital"}
              onClick={() => save("starting_capital", draft.starting_capital)}
            >
              {saved === "starting_capital" ? "Kaydedildi ✓" : "Kaydet"}
            </Button>
          </div>
        </Card>

        <Card>
          <h3 className="text-sm font-semibold text-ink mb-1">Maksimum pozisyon büyüklüğü ($)</h3>
          <p className="text-xs text-ink-soft mb-3">
            RiskEngine'in gerçek üst sınırı — AI, işlem başına hesaplanan payı bu değerin üzerindeyse
            pozisyonu reddeder (SIZE_EXCEEDED). Kasa/pay/eşzamanlılık ayarlarından (yukarıda ve solda)
            AYRI bir tablo — biri değişince diğerini elle güncellemeniz gerekir.
          </p>
          {computedCapitalPerTrade != null && (
            <p className={`text-xs mb-3 ${
              maxPositionSize && computedCapitalPerTrade > Number(maxPositionSize) ? "text-fall" : "text-ink-faint"
            }`}>
              Şu anki kasa ayarlarına göre işlem başı hesaplanan pay: {computedCapitalPerTrade.toLocaleString()}
              {maxPositionSize && computedCapitalPerTrade > Number(maxPositionSize) && (
                <> — bu, aşağıdaki limitten BÜYÜK, her işlem reddedilir.</>
              )}
            </p>
          )}
          {limitError && <p className="text-xs text-fall mb-3">{limitError}</p>}
          <div className="flex gap-2">
            <Input
              type="number"
              value={maxPositionSizeInput}
              onChange={setMaxPositionSizeInput}
            />
            <Button disabled={savingLimit} onClick={saveMaxPositionSize}>
              {savingLimit ? "Kaydediliyor…" : savedLimit ? "Kaydedildi ✓" : "Kaydet"}
            </Button>
          </div>
        </Card>

        <Card>
          <h3 className="text-sm font-semibold text-ink mb-1">İki işlem arası min. bekleme (sn)</h3>
          <p className="text-xs text-ink-soft mb-3">Test modunda bile geçerli — AI aynı sembolde art arda anlamsız işlem açmasın.</p>
          <div className="flex gap-2">
            <Input
              type="number"
              value={draft.min_seconds_between_trades ?? ""}
              onChange={(v) => setDraft((d) => ({ ...d, min_seconds_between_trades: v }))}
            />
            <Button
              disabled={saving === "min_seconds_between_trades"}
              onClick={() => save("min_seconds_between_trades", draft.min_seconds_between_trades)}
            >
              {saved === "min_seconds_between_trades" ? "Kaydedildi ✓" : "Kaydet"}
            </Button>
          </div>
        </Card>

        <Card>
          <h3 className="text-sm font-semibold text-ink mb-1">Stop/hedef mesafesi</h3>
          <p className="text-xs text-ink-soft mb-3">
            Pozisyonlar hiçbir zaman süre yüzünden zorla kapatılmaz — sadece gerçekten stop veya hedefe
            ulaşınca. Bu seçim, o stop/hedefin ne kadar UZAKTA olacağını belirler: dar bir mesafe (Scalp)
            genelde saatler içinde sonuçlanır, geniş bir mesafe (Swing) günler/haftalar sürebilir.
          </p>
          <div className="flex flex-col gap-2">
            {Object.entries(HORIZON_LABELS).map(([key, label]) => (
              <button
                key={key}
                onClick={() => save("trade_horizon", key)}
                className={`text-left px-3 py-2 rounded-lg text-sm border transition-colors ${
                  settings.trade_horizon === key
                    ? "bg-accent text-white border-accent"
                    : "bg-canvas-soft text-ink-soft border-line hover:bg-surface-soft"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </Card>

        <Card>
          <h3 className="text-sm font-semibold text-ink mb-1">Analiz mum aralığı</h3>
          <p className="text-xs text-ink-soft mb-3">
            Ajanların (RSI/EMA/ATR/Hurst vb.) sinyal ürettiği mum aralığı — işlem vadesinden ayrı, "4 saat"
            seçmek pozisyonun 4 saat açık kalacağı anlamına gelmez, sadece daha geniş bir bağlamdan sinyal
            üretilir.
          </p>
          <div className="flex flex-wrap gap-2 mb-4">
            {Object.entries(CANDLE_TIMEFRAME_LABELS).map(([key, label]) => (
              <button
                key={key}
                onClick={() => save("candle_timeframe", key)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                  settings.candle_timeframe === key
                    ? "bg-accent text-white border-accent"
                    : "bg-canvas-soft text-ink-soft border-line hover:bg-surface-soft"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <p className="text-xs text-ink-soft mb-2">
            Geçmiş pencere (kaç bar): 20-5000 arası (1000'in üzerinde Binance'e art arda istek atılır —
            daha yüksek gecikme, ama uzun-vade trend rejimi göstergesi için gerekli).
          </p>
          <div className="flex gap-2">
            <Input
              type="number"
              value={draft.candle_lookback ?? ""}
              onChange={(v) => setDraft((d) => ({ ...d, candle_lookback: v }))}
            />
            <Button
              disabled={saving === "candle_lookback"}
              onClick={() => save("candle_lookback", draft.candle_lookback)}
            >
              {saved === "candle_lookback" ? "Kaydedildi ✓" : "Kaydet"}
            </Button>
          </div>
        </Card>

        <Card>
          <h3 className="text-sm font-semibold text-ink mb-1">Görüntüleme para birimi</h3>
          <p className="text-xs text-ink-soft mb-3">
            Sistemdeki tüm fiyat/PnL hesaplamaları her zaman USD cinsinden yapılır (kripto çiftleri
            USDT'ye, hisse/endeks zaten USD'ye endeksli) — bu sadece dashboard'da nasıl GÖRÜNTÜLENECEĞİni
            değiştirir, gerçek, canlı kurlarla (Binance BTCUSDT / USDTTRY) anlık dönüştürülür.
          </p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(DISPLAY_CURRENCY_LABELS).map(([key, label]) => (
              <button
                key={key}
                onClick={() => save("display_currency", key)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                  settings.display_currency === key
                    ? "bg-accent text-white border-accent"
                    : "bg-canvas-soft text-ink-soft border-line hover:bg-surface-soft"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </Card>

        <Card>
          <h3 className="text-sm font-semibold text-ink mb-1">Görünüm</h3>
          <p className="text-xs text-ink-soft mb-3">
            Açık/Koyu tema — sadece bu tarayıcıda geçerli, sunucuya kaydedilmez. "Sistem" işletim
            sisteminin gece/gündüz tercihini takip eder.
          </p>
          <div className="flex gap-2">
            {(Object.entries(THEME_LABELS) as [ThemePreference, string][]).map(([key, label]) => (
              <button
                key={key}
                onClick={() => chooseTheme(key)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                  theme === key
                    ? "bg-accent text-white border-accent"
                    : "bg-canvas-soft text-ink-soft border-line hover:bg-surface-soft"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </Card>

        <Card>
          <h3 className="text-sm font-semibold text-ink mb-1">Orta vadeli pozisyon katmanı</h3>
          <p className="text-xs text-ink-soft mb-3">
            Kısa vadeli katmandan tamamen ayrı çalışır: kendi günlük/4 saatlik sinyaliyle, kendi ayrı
            sermaye havuzuyla (kısa vadelinin kasasını tüketmez). Kapalıyken hiçbir etkisi yok.
          </p>
          <div className="flex gap-2 mb-4">
            {[
              { key: "true", label: "Açık" },
              { key: "false", label: "Kapalı" },
            ].map(({ key, label }) => (
              <button
                key={key}
                onClick={() => save("medium_term_enabled", key)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                  (settings.medium_term_enabled ?? "false") === key
                    ? "bg-accent text-white border-accent"
                    : "bg-canvas-soft text-ink-soft border-line hover:bg-surface-soft"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <p className="text-xs text-ink-soft mb-2">Sinyal zaman dilimi</p>
          <div className="flex gap-2 mb-4">
            {[
              { key: "4h", label: "4 saat" },
              { key: "1d", label: "1 gün" },
            ].map(({ key, label }) => (
              <button
                key={key}
                onClick={() => save("medium_term_timeframe", key)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                  settings.medium_term_timeframe === key
                    ? "bg-accent text-white border-accent"
                    : "bg-canvas-soft text-ink-soft border-line hover:bg-surface-soft"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <p className="text-xs text-ink-soft mb-2">
            Sermaye payı (0-1 arası, ör. 0.1 = kasanın %10'u)
          </p>
          <div className="flex gap-2 mb-4">
            <Input
              decimal
              value={draft.medium_term_capital_pct ?? ""}
              onChange={(v) => setDraft((d) => ({ ...d, medium_term_capital_pct: v }))}
            />
            <Button
              disabled={saving === "medium_term_capital_pct"}
              onClick={() => save("medium_term_capital_pct", draft.medium_term_capital_pct)}
            >
              {saved === "medium_term_capital_pct" ? "Kaydedildi ✓" : "Kaydet"}
            </Button>
          </div>

          <p className="text-xs text-ink-soft mb-2">Aynı anda en fazla kaç orta-vadeli pozisyon</p>
          <div className="flex gap-2">
            <Input
              type="number"
              value={draft.medium_term_max_concurrent ?? ""}
              onChange={(v) => setDraft((d) => ({ ...d, medium_term_max_concurrent: v }))}
            />
            <Button
              disabled={saving === "medium_term_max_concurrent"}
              onClick={() => save("medium_term_max_concurrent", draft.medium_term_max_concurrent)}
            >
              {saved === "medium_term_max_concurrent" ? "Kaydedildi ✓" : "Kaydet"}
            </Button>
          </div>
        </Card>
      </div>
    </div>
  );
}
