import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { authHeaders } from "../api/auth";
import { PageHeader, Button, Badge, StatCard, Card, ErrorNote, EmptyState, Spinner } from "../components/ui";
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

// Faz 268-sonrası: kullanıcı isteği — "kill switch tetiklendiğinde bana
// bildirim gelmiyor." Health-check alarmıyla AYNI kanal (ses + masaüstü
// bildirimi), ama ayrı bir "tag" ile — ikisi birbirini ezmesin, ikisi de
// aynı anda görünebilsin.
function notifyKillSwitch() {
  playAlarmBeep();
  if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
  new Notification("⛔ Kill switch tetiklendi — AI durduruldu", {
    body: "Ardışık kayıp eşiği aşıldı — dashboard'dan manuel gözden geçirip tekrar açman gerekiyor.",
    tag: "kill-switch-alarm",
  });
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
      className="relative overflow-hidden rounded-xl border border-line glass-panel shadow-layer-1 hover:shadow-layer-2 p-6"
      style={
        isOn
          ? ({ "--glass-glow": `radial-gradient(120% 100% at 0% 0%, ${glowColor}14, transparent 60%)` } as CSSProperties)
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

// Faz 268ak — kullanıcı isteği: "Performance kısmı yanlış yerde, oradaki
// verileri direkt Dashboard'a gömsek hem daha sade olur hem Dashboard'da
// adam akıllı veri olur." Performance.tsx'in TÜM içeriği (all-time
// istatistikler + günlük/haftalık/aylık/yıllık tablo) buraya taşındı,
// Performance ayrı bir sayfa olmaktan çıktı.
type Bucket = {
  period_start: string;
  trade_count: number;
  total_pnl: number;
  win_rate: number;
  roi_pct: number;
  roi_pct_on_deployed: number;
};

type AllTime = {
  trade_count: number;
  total_pnl: number;
  win_rate: number;
  roi_pct: number;
  roi_pct_on_deployed: number;
  deployed_notional: number;
  excluded_dirty_trades_count: number;
  tp_count: number;
  sl_count: number;
  manual_count: number;
};

// Faz 268f — kullanıcı isteği: "kısa/orta/uzun swing scalp gibi işlem
// tiplerinden hangileri başarılı olmuş, dashboard'a otomatik yansısın."
// Transactions.tsx::tradeTypeBadge() ile AYNI sınıflandırma, backend'de
// (api/rest/positions.py::_classify_trade_type) agregasyonu yapılıyor.
type TradeTypeStat = { trade_count: number; win_rate: number; total_pnl: number };

type PerformanceData = {
  starting_capital: number;
  all_time: AllTime;
  daily: Bucket[];
  weekly: Bucket[];
  monthly: Bucket[];
  yearly: Bucket[];
  by_trade_type: Record<string, TradeTypeStat>;
};

const PERIOD_TABS: { key: keyof Pick<PerformanceData, "daily" | "weekly" | "monthly" | "yearly">; label: string }[] = [
  { key: "daily", label: "Günlük" },
  { key: "weekly", label: "Haftalık" },
  { key: "monthly", label: "Aylık" },
  { key: "yearly", label: "Yıllık" },
];

const TRADE_TYPE_LABELS: Record<string, string> = {
  scalp: "Scalp",
  gun_ici: "Gün içi",
  swing: "Swing",
  orta_vadeli: "Orta vadeli",
  hedge: "Hedge",
};
// En dar stoptan en genişe, sonra katman-tabanlı türler — okuma sırası
// anlamlı olsun diye (rastgele obje key sırası değil).
const TRADE_TYPE_ORDER = ["scalp", "gun_ici", "swing", "orta_vadeli", "hedge"];

export default function Dashboard() {
  const [settings, setSettings] = useState<SettingsMap>({});
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openCount, setOpenCount] = useState(0);
  const [perf, setPerf] = useState<PerformanceData | null>(null);
  const [periodTab, setPeriodTab] = useState<"daily" | "weekly" | "monthly" | "yearly">("daily");
  const [signalHealth, setSignalHealth] = useState<SignalHealth | null>(null);
  const [notifPermission, setNotifPermission] = useState<NotificationPermission | "unsupported">(
    typeof Notification === "undefined" ? "unsupported" : Notification.permission
  );
  const wasHealthyRef = useRef<boolean | null>(null);
  const lastAlarmAtRef = useRef<number>(0);
  // Faz 268-sonrası: kill switch bildirimi — health alarmıyla AYNI
  // yeniden-uyarma deseni ama ayrı bir ref/zamanlayıcı (ikisi bağımsız
  // olaylar, birbirinin renotify penceresini sıfırlamamalı).
  const wasKillSwitchedRef = useRef<boolean>(false);
  const lastKillSwitchAlarmAtRef = useRef<number>(0);
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

  const handleAiEnabledStatus = (aiEnabled: string | undefined, updatedBy: string | null | undefined) => {
    const isKillSwitched = aiEnabled === "false" && updatedBy === "kill_switch";
    const now = Date.now();
    if (isKillSwitched) {
      const isNewEpisode = !wasKillSwitchedRef.current;
      const dueForRenotify = now - lastKillSwitchAlarmAtRef.current > ALARM_RENOTIFY_MS;
      if (isNewEpisode || dueForRenotify) {
        notifyKillSwitch();
        lastKillSwitchAlarmAtRef.current = now;
      }
    }
    wasKillSwitchedRef.current = isKillSwitched;
  };

  const load = () => {
    fetch("/api/v1/settings/", { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => {
        setSettings(data.settings || {});
        handleAiEnabledStatus(data.settings?.ai_enabled, data.ai_enabled_updated_by);
      })
      .catch((e) => setError(String(e)));
    fetch("/api/v1/positions", { headers: authHeaders() })
      .then((r) => r.json())
      // Faz 262: kritik bulgu — (data.positions || []).length API'nin
      // limit=100 varsayılanına sabitliydi, gerçek açık pozisyon sayısı
      // (o an 1074) hiç yansımıyordu. summary.open_count limitsiz, gerçek
      // toplam.
      .then((data) => setOpenCount(data.summary?.open_count ?? (data.positions || []).length));
    fetch("/api/v1/performance", { headers: authHeaders() })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(setPerf)
      .catch((e) => setError(String(e.message || e)));
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

      {!perf && !error && (
        <div className="flex justify-center py-12">
          <Spinner />
        </div>
      )}

      {perf && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <StatCard label="Açık pozisyon" value={openCount} />
            <StatCard label="Kapanmış işlem" value={perf.all_time.trade_count} />
            <StatCard label="Kazanma oranı" value={`%${(perf.all_time.win_rate * 100).toFixed(0)}`} />
            <StatCard label="TP ile kapanan" value={perf.all_time.tp_count} tone="rise" />
            <StatCard label="SL ile kapanan" value={perf.all_time.sl_count} tone="fall" />
            <StatCard label="Manuel kapanan" value={perf.all_time.manual_count} />
            <StatCard
              label={`Toplam PnL (${currency})`}
              value={format(perf.all_time.total_pnl)}
              tone={perf.all_time.total_pnl > 0 ? "rise" : perf.all_time.total_pnl < 0 ? "fall" : "neutral"}
            />
            <StatCard
              label="Strateji getirisi"
              value={`%${(perf.all_time.roi_pct_on_deployed * 100).toFixed(3)}`}
              tone={perf.all_time.roi_pct_on_deployed > 0 ? "rise" : perf.all_time.roi_pct_on_deployed < 0 ? "fall" : "neutral"}
              sub={`kullanılan: ${format(perf.all_time.deployed_notional)}`}
            />
          </div>

          <p className="text-xs text-ink-soft mb-4">
            Kasa büyüklüğüne göre ROI: %{(perf.all_time.roi_pct * 100).toFixed(6)} (sermaye:{" "}
            {perf.starting_capital.toLocaleString()} — test için çok büyük bir değere ayarlıysa bu oran
            her zaman ~0 görünür, stratejinin gerçek performansı yukarıdaki "kullanılan sermayeye göre"
            değeridir).
          </p>

          {perf.all_time.excluded_dirty_trades_count > 0 && (
            <p className="text-xs text-ink-faint mb-4">
              Not: {perf.all_time.excluded_dirty_trades_count} adet kirli işlem (aşırı test ayarlarından kalan
              gerçek olmayan büyüklükteki işlemler ve geçmişte bir veri sağlayıcı hatası yüzünden gerçek dışı
              fiyatla kapanmış işlemler) yukarıdaki istatistiklerden hariç tutuldu (silinmedi, sadece
              istatistiklere dahil edilmedi).
            </p>
          )}

          <div className="flex gap-1 mb-4">
            {PERIOD_TABS.map((t) => (
              <button
                key={t.key}
                onClick={() => setPeriodTab(t.key)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium ${
                  periodTab === t.key ? "bg-accent text-white" : "bg-canvas-soft text-ink-soft hover:text-ink"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          {periodTab === "daily" && (
            <p className="text-xs text-ink-faint mb-3">
              "Günlük" burada takvim günü demek (UTC 00:00'dan itibaren) — Transactions sayfasındaki
              "Son 24 saat" ise şu andan geriye kayan bir pencere, gün sınırı gözetmez. Gün henüz
              birkaç saatliyken ikisi doğal olarak farklı sayı gösterebilir; Transactions'ta gerçekten
              aynı tanımı isteyen "Bugün (UTC takvim günü)" seçeneği var.
            </p>
          )}

          <Card padded={false}>
            {perf[periodTab].length === 0 ? (
              <div className="p-5">
                <EmptyState label="Bu dönem için henüz kapanmış işlem yok." />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-ink-faint uppercase tracking-wide border-b border-line-soft">
                      <th className="px-5 py-2 font-medium">Dönem</th>
                      <th className="px-5 py-2 font-medium">İşlem</th>
                      <th className="px-5 py-2 font-medium">Kazanma oranı</th>
                      <th className="px-5 py-2 font-medium">PnL</th>
                      <th className="px-5 py-2 font-medium">Strateji getirisi</th>
                    </tr>
                  </thead>
                  <tbody>
                    {perf[periodTab].map((b) => (
                      <tr key={b.period_start} className="border-b border-line-soft last:border-0">
                        <td className="px-5 py-2.5 text-ink-soft text-xs">
                          {new Date(b.period_start).toLocaleDateString()}
                        </td>
                        <td className="px-5 py-2.5 text-ink-soft">{b.trade_count}</td>
                        <td className="px-5 py-2.5">
                          <Badge tone={b.win_rate >= 0.5 ? "rise" : "fall"}>{(b.win_rate * 100).toFixed(0)}%</Badge>
                        </td>
                        <td className={`px-5 py-2.5 font-medium ${b.total_pnl >= 0 ? "text-rise" : "text-fall"}`}>
                          {format(b.total_pnl)}
                        </td>
                        <td className={`px-5 py-2.5 font-medium ${b.roi_pct_on_deployed >= 0 ? "text-rise" : "text-fall"}`}>
                          {(b.roi_pct_on_deployed * 100).toFixed(3)}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          {Object.keys(perf.by_trade_type || {}).length > 0 && (
            <>
              <h3 className="text-sm font-semibold text-ink-soft uppercase tracking-wide mb-3 mt-8">
                İşlem Tipine Göre Performans
              </h3>
              <p className="text-xs text-ink-faint mb-3">
                Scalp/gün içi/swing, pozisyonun gerçek stop mesafesinden (Transactions'taki rozetlerle aynı
                sınıflandırma) belirleniyor; orta vadeli ve hedge ayrı katman/mekanizmalar.
              </p>
              <Card padded={false}>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs text-ink-faint uppercase tracking-wide border-b border-line-soft">
                        <th className="px-5 py-2 font-medium">Tür</th>
                        <th className="px-5 py-2 font-medium">İşlem</th>
                        <th className="px-5 py-2 font-medium">Kazanma oranı</th>
                        <th className="px-5 py-2 font-medium">PnL</th>
                      </tr>
                    </thead>
                    <tbody>
                      {TRADE_TYPE_ORDER.filter((t) => perf.by_trade_type[t]).map((t) => {
                        const stat = perf.by_trade_type[t];
                        return (
                          <tr key={t} className="border-b border-line-soft last:border-0">
                            <td className="px-5 py-2.5 text-ink font-medium">{TRADE_TYPE_LABELS[t] || t}</td>
                            <td className="px-5 py-2.5 text-ink-soft">{stat.trade_count}</td>
                            <td className="px-5 py-2.5">
                              <Badge tone={stat.win_rate >= 0.5 ? "rise" : "fall"}>
                                {(stat.win_rate * 100).toFixed(0)}%
                              </Badge>
                            </td>
                            <td className={`px-5 py-2.5 font-medium ${stat.total_pnl >= 0 ? "text-rise" : "text-fall"}`}>
                              {format(stat.total_pnl)}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </Card>
            </>
          )}
        </>
      )}
    </div>
  );
}
