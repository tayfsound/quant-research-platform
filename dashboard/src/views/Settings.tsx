import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Button, ErrorNote, Input } from "../components/ui";

type SettingsMap = Record<string, string>;

// Trader jargonunda üçü de "kısa vadeli" sayılır (haftalar/aylar sürmüyor)
// — "kısa/orta/uzun vadeli" etiketi yanıltıcıydı. Sistem zaten gün-içi
// işlem için tasarlı (ATR-tabanlı hedefler, saniyeler içinde kapanış
// kontrolü); gerçek çok haftalık/aylık swing/pozisyon trading ayrı bir iş.
const HORIZON_LABELS: Record<string, string> = {
  short: "Scalp (~10 dk)",
  medium: "Gün içi (~4 saat)",
  long: "1 günlük swing (~1 gün)",
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

  const load = () => {
    fetch("/api/v1/settings/", { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => {
        setSettings(data.settings || {});
        setDraft(data.settings || {});
      })
      .catch((e) => setError(String(e)));
  };

  useEffect(load, []);

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
              value={draft.min_profit_target_pct != null && draft.min_profit_target_pct !== "" ? String(Number(draft.min_profit_target_pct) * 100) : ""}
              onChange={(v) => setDraft((d) => ({ ...d, min_profit_target_pct: v === "" ? "" : String(Number(v) / 100) }))}
            />
            <Button
              disabled={saving === "min_profit_target_pct"}
              onClick={() => save("min_profit_target_pct", draft.min_profit_target_pct)}
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
          <h3 className="text-sm font-semibold text-ink mb-1">İşlem vadesi</h3>
          <p className="text-xs text-ink-soft mb-3">
            AI kısa vadeli işlemlere yönelsin, orta/uzun vadeli pozisyonlar açıp kasayı kilitlemesin istiyorsan "Kısa vadeli" seç.
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
          <h3 className="text-sm font-semibold text-ink mb-1">Token bazlı kaldıraç</h3>
          <p className="text-xs text-ink-soft mb-3">
            Her sembol için ayrı kaldıraç ayarlayabilirsin (ör. altın 25x, BTC 10x, XRP 3x). Boş/1
            bırakılan bir sembol spot (kaldıraçsız) işlem görür — likidasyon fiyatı gerçekten hesaplanıp
            takip edilir, kaldıraçlı bir pozisyon likidasyona uğrarsa sistem bunu görmezden gelmez.
          </p>
          <div className="space-y-2">
            {(draft.watchlist ?? settings.watchlist ?? "")
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean)
              .map((symbol) => {
                let leverageMap: Record<string, number> = {};
                try {
                  leverageMap = JSON.parse(settings.symbol_leverage || "{}");
                } catch {
                  leverageMap = {};
                }
                const draftMap: Record<string, string> =
                  (draft as any)._leverageDraft || {};
                const current = draftMap[symbol] ?? String(leverageMap[symbol] ?? 1);
                return (
                  <div key={symbol} className="flex items-center gap-2">
                    <span className="w-24 font-mono text-xs text-ink-soft">{symbol}</span>
                    <Input
                      type="number"
                      value={current}
                      onChange={(v) =>
                        setDraft((d) => ({
                          ...d,
                          _leverageDraft: { ...((d as any)._leverageDraft || {}), [symbol]: v },
                        } as any))
                      }
                    />
                    <Button
                      disabled={saving === "symbol_leverage"}
                      onClick={() => {
                        const nextLeverage = Math.max(1, parseFloat(current) || 1);
                        const nextMap = { ...leverageMap, [symbol]: nextLeverage };
                        save("symbol_leverage", JSON.stringify(nextMap));
                      }}
                    >
                      Kaydet
                    </Button>
                  </div>
                );
              })}
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
              type="number"
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
