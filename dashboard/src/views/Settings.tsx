import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Button, Badge, ErrorNote, Input } from "../components/ui";

type SettingsMap = Record<string, string>;

const HORIZON_LABELS: Record<string, string> = {
  short: "Kısa vadeli (~10 dk)",
  medium: "Orta vadeli (~4 saat)",
  long: "Uzun vadeli (~1 gün)",
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

  const isLive = settings.trading_mode === "live";
  const isRunning = settings.ai_enabled !== "false";

  return (
    <div>
      <PageHeader
        title="Settings"
        description="Bunlar AI'ın değil, senin belirlediğin kurallar — kaç işlem aynı anda açık olabilir, kasanın max yüzde kaçı kullanılabilir, işlemler ne kadar vadeli olsun."
      />

      {error && <ErrorNote>{error}</ErrorNote>}

      <Card className="mb-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <h3 className="text-sm font-semibold text-ink">AI Durumu</h3>
              <Badge tone={isRunning ? "rise" : "neutral"}>{isRunning ? "ÇALIŞIYOR" : "DURDURULDU"}</Badge>
            </div>
            <p className="text-xs text-ink-soft max-w-md">
              {isRunning
                ? "AI yeni pozisyon açabiliyor. Durdurursan yeni işlem almaz, ama açık pozisyonların vadesi dolduğunda/hedefine ulaştığında normal şekilde kapanmaya devam eder."
                : "AI durduruldu — yeni pozisyon açmıyor. Mevcut açık pozisyonlar etkilenmez, normal şekilde kapanmaya devam ediyor."}
            </p>
          </div>
          <Button
            variant={isRunning ? "danger" : "primary"}
            disabled={saving === "ai_enabled"}
            onClick={() => save("ai_enabled", isRunning ? "false" : "true")}
          >
            {isRunning ? "Durdur" : "Başlat"}
          </Button>
        </div>
      </Card>

      <Card className="mb-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <h3 className="text-sm font-semibold text-ink">İşlem Modu</h3>
              <Badge tone={isLive ? "fall" : "accent"}>{isLive ? "LIVE" : "TEST"}</Badge>
            </div>
            <p className="text-xs text-ink-soft max-w-md">
              {isLive
                ? "Live modda: aşağıdaki tüm kurallar (pozisyon sayısı, sermaye yüzdesi) gerçekten uygulanır."
                : "Test modunda: AI sınırsız deneme yapabilir, hiçbir kural uygulanmaz. Her şeyin düzgün çalıştığından emin olunca Live'a geç."}
            </p>
          </div>
          <Button
            variant={isLive ? "secondary" : "primary"}
            disabled={saving === "trading_mode"}
            onClick={() => save("trading_mode", isLive ? "test" : "live")}
          >
            {isLive ? "Test moduna dön" : "Live moda geç"}
          </Button>
        </div>
      </Card>

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
