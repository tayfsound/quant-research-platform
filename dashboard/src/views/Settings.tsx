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
            {resetting ? "Sıfırlanıyor…" : resetDone ? "Sıfırlandı ✓" : "Varsayılanlara dön"}
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
          <p className="text-xs text-ink-soft mb-2">Geçmiş pencere (kaç bar): 20-1000 arası.</p>
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
      </div>
    </div>
  );
}
