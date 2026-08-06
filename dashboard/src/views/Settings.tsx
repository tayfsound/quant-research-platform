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

export default function Settings() {
  const [settings, setSettings] = useState<SettingsMap>({});
  const [draft, setDraft] = useState<SettingsMap>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

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
      />

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
            0.005 = hedefin fiyatın en az %0.5'i olması şart, yoksa işlem açılmaz. Komisyonu
            karşılamayan çok küçük hedefleri eler (gerçek olay: hedefe ulaştı ama komisyon kârı
            yedi). 0 = kapalı.
          </p>
          <div className="flex gap-2">
            <Input
              type="number"
              value={draft.min_profit_target_pct ?? ""}
              onChange={(v) => setDraft((d) => ({ ...d, min_profit_target_pct: v }))}
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
      </div>
    </div>
  );
}
