import { useEffect, useRef, useState } from "react";
import { authHeaders } from "../api/auth";
import { PageHeader, Button, Badge, StatCard, ErrorNote } from "../components/ui";
import { useCurrency } from "../lib/currency";

type SettingsMap = Record<string, string>;

// Faz 242: kullanıcı isteği — pasif banner yetmiyor, sayfaya bakılmadığı
// sürece fark edilmiyor. Web Audio API ile (dışarıdan ses dosyası
// gerektirmeden) kısa bir alarm sesi + Notification API ile sekme
// arka plandayken de görünen masaüstü bildirimi. İlk unhealthy anında
// VE sonrasında sorun devam ederse her 5 dakikada bir tekrar uyarır
// (tek seferlik bildirim kolayca kaçırılır).
const ALARM_RENOTIFY_MS = 5 * 60 * 1000;

function playAlarmBeep() {
  try {
    const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    [0, 220, 440].forEach((delayMs, i) => {
      setTimeout(() => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "sine";
        osc.frequency.value = i % 2 === 0 ? 880 : 660;
        gain.gain.setValueAtTime(0.15, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.18);
        osc.connect(gain).connect(ctx.destination);
        osc.start();
        osc.stop(ctx.currentTime + 0.2);
      }, delayMs);
    });
  } catch {
    // Ses çalınamıyorsa (ör. tarayıcı kısıtlaması) sessizce geç —
    // masaüstü bildirimi zaten ayrı bir kanal.
  }
}

function notifyUnhealthy(unhealthyLabels: string[]) {
  if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
  new Notification("⚠ Trading sistemi sessiz kalmış olabilir", {
    body: unhealthyLabels.join(", "),
    tag: "signal-health-alarm",
  });
}

function notifyRecovered() {
  if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
  new Notification("✓ Sistem normale döndü", { tag: "signal-health-alarm" });
}

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
      className="relative overflow-hidden rounded-xl border border-line bg-surface/75 backdrop-blur-xl shadow-layer-1 hover:shadow-layer-2 p-6"
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

type SignalHealth = {
  healthy: boolean;
  checks: Record<string, { healthy?: boolean; age_seconds?: number; ai_enabled?: boolean; reason?: string }>;
};

const HEALTH_CHECK_LABELS: Record<string, string> = {
  candle_ingestion: "Mum verisi",
  order_book_ingestion: "Order book verisi",
  trading_cycle: "Trading cycle",
  zombie_wait: "Yönlü karar üretimi",
};

export default function Dashboard() {
  const [settings, setSettings] = useState<SettingsMap>({});
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openCount, setOpenCount] = useState(0);
  const [summary, setSummary] = useState<{ count: number; win_rate: number; total_pnl: number } | null>(null);
  const [signalHealth, setSignalHealth] = useState<SignalHealth | null>(null);
  const [notifPermission, setNotifPermission] = useState<NotificationPermission | "unsupported">(
    typeof Notification === "undefined" ? "unsupported" : Notification.permission
  );
  const wasHealthyRef = useRef<boolean | null>(null);
  const lastAlarmAtRef = useRef<number>(0);
  const { format, currency } = useCurrency();

  const handleSignalHealth = (data: SignalHealth) => {
    setSignalHealth(data);
    const now = Date.now();
    if (!data.healthy) {
      const isNewEpisode = wasHealthyRef.current !== false;
      const dueForRenotify = now - lastAlarmAtRef.current > ALARM_RENOTIFY_MS;
      if (isNewEpisode || dueForRenotify) {
        const unhealthyLabels = Object.entries(data.checks)
          .filter(([, v]) => v.healthy === false)
          .map(([key]) => HEALTH_CHECK_LABELS[key] || key);
        playAlarmBeep();
        notifyUnhealthy(unhealthyLabels);
        lastAlarmAtRef.current = now;
      }
    } else if (wasHealthyRef.current === false) {
      notifyRecovered();
    }
    wasHealthyRef.current = data.healthy;
  };

  const load = () => {
    fetch("/api/v1/settings/", { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => setSettings(data.settings || {}))
      .catch((e) => setError(String(e)));
    fetch("/api/v1/positions", { headers: authHeaders() })
      .then((r) => r.json())
      // Faz 262: kritik bulgu — (data.positions || []).length API'nin
      // limit=100 varsayılanına sabitliydi, gerçek açık pozisyon sayısı
      // (o an 1074) hiç yansımıyordu. summary.open_count limitsiz, gerçek
      // toplam.
      .then((data) => setOpenCount(data.summary?.open_count ?? (data.positions || []).length));
    fetch("/api/v1/trades", { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => setSummary(data.summary || null));
    // Faz 230: kullanıcı isteği — "sistem sessiz kalırsa alarma geçecek mi?"
    // Faz 203-211'deki 7 katmanlı sessiz-hata zincirinin (sistem çalışıyor
    // görünüp hiç gerçek işlem açmıyordu) bir daha fark edilmeden
    // yaşanmaması için — bkz. observability/signal_health.py.
    fetch("/health/signals")
      .then((r) => r.json())
      .then(handleSignalHealth)
      .catch(() => {});
  };

  const requestNotifPermission = () => {
    if (typeof Notification === "undefined") return;
    Notification.requestPermission().then(setNotifPermission);
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

      {notifPermission === "default" && (
        <div className="mb-6 rounded-xl border border-line bg-canvas-soft p-4 flex items-center justify-between gap-4">
          <p className="text-xs text-ink-soft">
            Sistem sessiz kalırsa (uzun süre işlem açmazsa) masaüstü bildirimi + sesli alarm almak ister misin?
          </p>
          <Button variant="secondary" onClick={requestNotifPermission}>Bildirimleri etkinleştir</Button>
        </div>
      )}

      {signalHealth && !signalHealth.healthy && (
        <div className="mb-6 rounded-xl border border-fall/20 bg-fall-soft p-4">
          <p className="text-sm font-semibold text-fall mb-2">
            ⚠ Sistem sessiz kalmış olabilir — bazı modüller beklenenden uzun süredir güncel veri üretmiyor.
          </p>
          <ul className="text-xs text-ink-soft space-y-1">
            {Object.entries(signalHealth.checks)
              .filter(([, v]) => v.healthy === false)
              .map(([key, v]) => (
                <li key={key}>
                  <span className="font-medium text-ink">{HEALTH_CHECK_LABELS[key] || key}</span>
                  {v.age_seconds != null && ` — son güncelleme ${Math.round(v.age_seconds / 60)} dakika önce`}
                  {key === "zombie_wait" && " — son 30 karar hiç yönlü (LONG/SHORT) değil, sadece WAIT"}
                </li>
              ))}
          </ul>
          {notifPermission === "denied" && (
            <p className="text-xs text-ink-faint mt-2">
              Not: tarayıcı bildirimleri engellenmiş — sadece sesli alarm çalıyor. Bildirimleri açmak için
              tarayıcı adres çubuğundaki site ayarlarından izin verebilirsin.
            </p>
          )}
        </div>
      )}

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
              : "Live ile AYNI kasa/pozisyon/işlem-sıklığı kuralları uygulanıyor — tek fark, düşük güvenli sinyaller de (küçük boyutta) denenip gerçek sonuç biriktirebiliyor. Emin olunca Live'a geç."
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
