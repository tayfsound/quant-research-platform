import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { PageHeader, Button, Badge, StatCard, ErrorNote } from "../components/ui";
import { useCurrency } from "../lib/currency";

type SettingsMap = Record<string, string>;

function StatusCard({
  eyebrow,
  title,
  description,
  isOn,
  onLabel,
  offLabel,
  actionOnLabel,
  actionOffLabel,
  glow,
  loading,
  onToggle,
}: {
  eyebrow: string;
  title: string;
  description: string;
  isOn: boolean;
  onLabel: string;
  offLabel: string;
  actionOnLabel: string;
  actionOffLabel: string;
  glow: "rise" | "accent";
  loading: boolean;
  onToggle: () => void;
}) {
  const glowColor = glow === "rise" ? "var(--color-rise)" : "var(--color-accent)";
  return (
    <div
      className="relative overflow-hidden rounded-xl border border-line bg-surface shadow-layer-1 hover:shadow-layer-2 p-6"
      style={
        isOn
          ? { backgroundImage: `radial-gradient(120% 100% at 0% 0%, ${glowColor}14, transparent 60%)` }
          : undefined
      }
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[11px] uppercase tracking-wider text-ink-faint font-semibold mb-1">{eyebrow}</p>
          <div className="flex items-center gap-2 mb-2">
            <span
              className={`w-2 h-2 rounded-full ${isOn ? (glow === "rise" ? "bg-rise" : "bg-accent") : "bg-ink-faint"}`}
              style={isOn ? { boxShadow: `0 0 0 4px ${glowColor}22` } : undefined}
            />
            <h3 className="text-lg font-semibold text-ink tracking-tight">{title}</h3>
          </div>
          <p className="text-sm text-ink-soft max-w-sm leading-relaxed">{description}</p>
        </div>
        <Badge tone={isOn ? (glow === "rise" ? "rise" : "accent") : "neutral"}>
          {isOn ? onLabel : offLabel}
        </Badge>
      </div>
      <Button
        variant={isOn ? "secondary" : "primary"}
        disabled={loading}
        onClick={onToggle}
        className="mt-5"
      >
        {isOn ? actionOffLabel : actionOnLabel}
      </Button>
    </div>
  );
}

export default function Dashboard() {
  const [settings, setSettings] = useState<SettingsMap>({});
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openCount, setOpenCount] = useState(0);
  const [summary, setSummary] = useState<{ count: number; win_rate: number; total_pnl: number } | null>(null);
  const { format, currency } = useCurrency();

  const load = () => {
    fetch("/api/v1/settings/", { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => setSettings(data.settings || {}))
      .catch((e) => setError(String(e)));
    fetch("/api/v1/positions", { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => setOpenCount((data.positions || []).length));
    fetch("/api/v1/trades", { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => setSummary(data.summary || null));
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 15000);
    return () => clearInterval(interval);
  }, []);

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
      })
      .catch((e) => setError(`${key}: ${e.message || e}`))
      .finally(() => setSaving(null));
  };

  const isRunning = settings.ai_enabled !== "false";
  const isLive = settings.trading_mode === "live";

  return (
    <div>
      <PageHeader title="Dashboard" description="AI'ın şu anki durumu ve gerçek zamanlı özet." />

      {error && <ErrorNote>{error}</ErrorNote>}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <StatusCard
          eyebrow="AI Durumu"
          title={isRunning ? "Çalışıyor" : "Durduruldu"}
          description={
            isRunning
              ? "Yeni pozisyon açabiliyor. Durdurursan yeni işlem almaz, açık pozisyonlar normal şekilde kapanmaya devam eder."
              : "Yeni pozisyon açmıyor. Mevcut açık pozisyonlar etkilenmeden kapanmaya devam ediyor."
          }
          isOn={isRunning}
          onLabel="Çalışıyor"
          offLabel="Durduruldu"
          actionOnLabel="Başlat"
          actionOffLabel="Durdur"
          glow="rise"
          loading={saving === "ai_enabled"}
          onToggle={() => save("ai_enabled", isRunning ? "false" : "true")}
        />
        <StatusCard
          eyebrow="İşlem Modu"
          title={isLive ? "Live" : "Test"}
          description={
            isLive
              ? "Kasa/pozisyon/işlem-sıklığı kuralları gerçekten uygulanıyor."
              : "AI sınırsız deneyebiliyor, kural uygulanmıyor. Emin olunca Live'a geç."
          }
          isOn={isLive}
          onLabel="Live"
          offLabel="Test"
          actionOnLabel="Live'a geç"
          actionOffLabel="Test'e dön"
          glow="accent"
          loading={saving === "trading_mode"}
          onToggle={() => save("trading_mode", isLive ? "test" : "live")}
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatCard label="Açık pozisyon" value={openCount} />
        <StatCard
          label="Kapanmış işlem"
          value={summary?.count ?? 0}
          sub={summary ? `%${(summary.win_rate * 100).toFixed(0)} kazanma oranı` : undefined}
        />
        <StatCard
          label={`Toplam PnL (${currency})`}
          value={summary ? format(summary.total_pnl) : "—"}
          tone={summary && summary.total_pnl > 0 ? "rise" : summary && summary.total_pnl < 0 ? "fall" : "neutral"}
        />
      </div>
    </div>
  );
}
