import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { authHeaders } from "../api/auth";
import { PageHeader, Button, Badge, StatCard, Card, ErrorNote, EmptyState, Spinner, Input } from "../components/ui";
import { useCurrency } from "../lib/currency";

type SettingsMap = Record<string, string>;

// Faz 268-sonrası — kullanıcı isteği: "scalp, gün içi, orta vade vs.
// farklı işlem türlerinin ne kadarı short ne kadarı long pozisyonmuş."
// Aşağıdaki TRADE_TYPE_LABELS/TRADE_TYPE_ORDER (bu dosyada zaten var,
// "İşlem Tipine Göre Performans" tablosunda kullanılıyor) BURADA da
// tekrar kullanılıyor — aynı kategoriler, aynı Türkçe etiketler, tek
// gerçek kaynak.
type TradeTypeBreakdownRow = { trade_type: string; direction: "LONG" | "SHORT"; position_count: number };

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
  manual_full_count: number;
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

// Faz 268-sonrası — kullanıcı isteği: günlük tablo sabit 15 satır yerine
// içinde bulunulan ayın gerçek gün sayısı kadar göstersin (Şubat 28/29,
// 30 günlük aylar, 31 günlük aylar — otomatik).
function daysInMonth(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate();
}
const daysInCurrentMonth = daysInMonth(new Date());

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
  pump_fade: "Pump-Fade",
};
// En dar stoptan en genişe, sonra katman-tabanlı türler — okuma sırası
// anlamlı olsun diye (rastgele obje key sırası değil).
//
// Kullanıcı bulgusu: backend api/rest/positions.py::_classify_trade_type
// "pump_fade" türünü zaten döndürüyordu (gerçek 2 kapanmış işlem, ikisi
// de kârlı) ama bu sabit liste dışında kaldığı için tabloda hiç
// görünmüyordu — TRADE_TYPE_ORDER.filter(...) listede olmayan hiçbir
// key'i render etmiyor, backend'in döndürdüğü YENİ bir tür sessizce
// kayboluyordu.
const TRADE_TYPE_ORDER = ["scalp", "gun_ici", "swing", "orta_vadeli", "hedge", "pump_fade"];

// Kullanıcı isteği: "işlem türüne göre açık pozisyonlar diye bir yer
// eklemişsin güzel ama kapanmış işlemlerin olduğu kısıma ratioları
// eklememişsin oradaki bilgiye de ihtiyacım var." Açık pozisyonlar için
// yazılan tablo, hem açık hem kapanmış için tekrar kullanılabilsin diye
// ortak bir bileşene çıkarıldı.
function TradeTypeBreakdownTable({ title, description, rows }: { title: string; description: string; rows: TradeTypeBreakdownRow[] }) {
  if (rows.length === 0) return null;
  return (
    <Card className="mb-6">
      <h3 className="text-sm font-semibold text-ink mb-1">{title}</h3>
      <p className="text-xs text-ink-soft mb-3">{description}</p>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-ink-faint border-b border-line-soft">
              <th className="py-2 pr-4">İşlem türü</th>
              <th className="py-2 pr-4">Long</th>
              <th className="py-2 pr-4">Short</th>
              <th className="py-2 pr-4">Toplam</th>
              <th className="py-2 pr-4">Long oranı</th>
            </tr>
          </thead>
          <tbody>
            {TRADE_TYPE_ORDER.filter((t) => rows.some((r) => r.trade_type === t)).map((type) => {
              const long = rows.find((r) => r.trade_type === type && r.direction === "LONG")?.position_count ?? 0;
              const short = rows.find((r) => r.trade_type === type && r.direction === "SHORT")?.position_count ?? 0;
              const total = long + short;
              return (
                <tr key={type} className="border-b border-line-soft/50">
                  <td className="py-2 pr-4 text-ink font-medium">{TRADE_TYPE_LABELS[type] || type}</td>
                  <td className="py-2 pr-4 text-rise">{long}</td>
                  <td className="py-2 pr-4 text-fall">{short}</td>
                  <td className="py-2 pr-4 text-ink-soft">{total}</td>
                  <td className="py-2 pr-4 text-ink-soft">{total > 0 ? `%${((long / total) * 100).toFixed(0)}` : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export default function Dashboard() {
  const [settings, setSettings] = useState<SettingsMap>({});
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openCount, setOpenCount] = useState(0);
  const [typeBreakdown, setTypeBreakdown] = useState<TradeTypeBreakdownRow[]>([]);
  const [closedTypeBreakdown, setClosedTypeBreakdown] = useState<TradeTypeBreakdownRow[]>([]);
  const [perf, setPerf] = useState<PerformanceData | null>(null);
  const [periodTab, setPeriodTab] = useState<"daily" | "weekly" | "monthly" | "yearly">("daily");
  // Faz 268f-sonrası: kullanıcı bulgusu — zero-fill düzeltmesiyle her
  // dönem sekmesi artık veri olmasa bile onlarca boş satır döndürüyor,
  // veri arttıkça aranan tarihi bulmak zorlaşacaktı. Basit istemci-taraflı
  // aralık filtresi — backend'e yeni bir parametre eklemeye gerek yok,
  // veri zaten tek seferde (limit=200 bucket) geliyor.
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [signalHealth, setSignalHealth] = useState<SignalHealth | null>(null);
  // Faz 268-sonrası — kullanıcı isteği: "Concept Drift aktif olduğunda
  // dashboard'da göreyim, sistem neden pozisyon almıyor bilmeden
  // kalmayayım." RiskEngine'in AYNI eşiği/hesabıyla (services/risk_state.
  // py::get_concept_drift_diagnostics) — burada ayrı bir kopya mantık yok.
  const [conceptDrift, setConceptDrift] = useState<{
    available: boolean; active?: boolean; enforced?: boolean;
    baseline_win_rate?: number; recent_win_rate?: number; p_value?: number;
  } | null>(null);
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
    fetch("/api/v1/positions/breakdown-by-type", { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => setTypeBreakdown(data.breakdown || []))
      .catch(() => setTypeBreakdown([]));
    fetch("/api/v1/trades/breakdown-by-type", { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => setClosedTypeBreakdown(data.breakdown || []))
      .catch(() => setClosedTypeBreakdown([]));
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
    fetch("/api/v1/dashboard/concept-drift-status", { headers: authHeaders() })
      .then((r) => r.json())
      .then(setConceptDrift)
      .catch(() => setConceptDrift(null));
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

      {conceptDrift?.available && conceptDrift.active && conceptDrift.enforced && (
        <div className="mb-6 rounded-xl border border-fall/20 bg-fall-soft p-4">
          <p className="text-sm font-semibold text-fall mb-1">
            ⚠ Concept Drift koruması aktif — yeni pozisyon açılmıyor
          </p>
          <p className="text-xs text-ink-soft">
            Bunun öncesindeki 100 işlemde kazanma oranı {((conceptDrift.baseline_win_rate ?? 0) * 100).toFixed(1)}%
            iken son 50 işlemde {((conceptDrift.recent_win_rate ?? 0) * 100).toFixed(1)}%'e düştü — bu, genel/tüm-zamanlar
            kazanma oranından FARKLI, sadece en yakın 150 kapanan işlemin kendi içindeki karşılaştırması
            (p={(conceptDrift.p_value ?? 0).toFixed(4)},
            istatistiksel olarak anlamlı) — sistem bunu kendi güvenlik mekanizması olarak algılayıp yeni işlem
            açmayı durdurdu. Zaten açık pozisyonlar etkilenmez, normal şekilde kapanmaya devam eder. Yakın
            pencere yeterince gerçek/sağlıklı kapanışla dolunca kendiliğinden açılır.
          </p>
        </div>
      )}

      {/* Faz 268-sonrası — kullanıcı isteği: "test modunda çalışmasın."
          Koruma artık sadece canlı modda pozisyon engelliyor (services/
          risk_state.py). Test modunda tespit edilse bile SADECE
          bilgilendirme — alarm rengi değil, "engellenmiyor" net belirtiliyor. */}
      {conceptDrift?.available && conceptDrift.active && !conceptDrift.enforced && (
        <div className="mb-6 rounded-xl border border-warn/20 bg-warn-soft p-4">
          <p className="text-sm font-semibold text-warn mb-1">
            ℹ Concept Drift tespit edildi — test modunda olduğun için pozisyon açmayı engellemiyor
          </p>
          <p className="text-xs text-ink-soft">
            Bunun öncesindeki 100 işlemde kazanma oranı {((conceptDrift.baseline_win_rate ?? 0) * 100).toFixed(1)}%
            iken son 50 işlemde {((conceptDrift.recent_win_rate ?? 0) * 100).toFixed(1)}%'e düştü — bu, genel/tüm-zamanlar
            kazanma oranından FARKLI, sadece en yakın 150 kapanan işlemin kendi içindeki karşılaştırması
            (p={(conceptDrift.p_value ?? 0).toFixed(4)},
            istatistiksel olarak anlamlı). Bu koruma sadece canlı modda gerçek pozisyon açmayı durdurur —
            test modunda amaç zaten veri biriktirmek olduğu için burada sadece bilgi amaçlı gösteriliyor.
          </p>
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
            {/* Faz 268-sonrası — kullanıcı isteği: manuel kapanışlar artık
                ayrı bir kova olarak gösterilmiyor, gerçek sonuçlarına göre
                (kârlıysa TP, zarardaysa SL) yukarıdaki iki karta dahil
                ediliyor (bkz. decision_persistor.py::closed_trades_summary). */}
            <StatCard label="TP ile kapanan" value={perf.all_time.tp_count} tone="rise" />
            <StatCard label="SL ile kapanan" value={perf.all_time.sl_count} tone="fall" />
            {/* Faz 311 — kullanıcı isteği (uzun süredir bekleyen todo):
                toplam manuel kapanan işlem sayısı. Yukarıdaki TP/SL
                kapanışlarının bir ALT KÜMESİ (manual_full kendi sonucuna
                göre zaten TP/SL'ye dahil edildi) — ayrı bir üçüncü kova
                DEĞİL, sadece "kaç işlemi elle kapattım" sorusuna
                bilgilendirici bir cevap. */}
            <StatCard label="Manuel kapanan (toplam)" value={perf.all_time.manual_full_count} />
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

          <TradeTypeBreakdownTable
            title="İşlem türüne göre açık pozisyonlar"
            description="Scalp/gün içi/orta vadeli/swing stop mesafesine ve zaman dilimine göre; Pump-Fade ve hedge kendi mekanik stratejilerinin etiketiyle ayrılıyor (bkz. Transactions'taki aynı rozetler)."
            rows={typeBreakdown}
          />

          <TradeTypeBreakdownTable
            title="İşlem türüne göre kapanmış işlemler"
            description="Aynı sınıflandırma, kapanmış işlemler üzerinden — hangi türün ne kadarı long/short olarak alınmış, gerçekleşmiş."
            rows={closedTypeBreakdown}
          />

          <p className="text-xs text-ink-soft mb-4">
            Kasa büyüklüğüne göre ROI: %{(perf.all_time.roi_pct * 100).toFixed(6)} (sermaye:{" "}
            {perf.starting_capital.toLocaleString()} — test için çok büyük bir değere ayarlıysa bu oran
            her zaman ~0 görünür, stratejinin gerçek performansı yukarıdaki "kullanılan sermayeye göre"
            değeridir).
          </p>

          {periodTab === "daily" && (
            <p className="text-xs text-ink-faint mb-3">
              "Günlük" burada takvim günü demek (UTC 00:00'dan itibaren) — Transactions sayfasındaki
              "Son 24 saat" ise şu andan geriye kayan bir pencere, gün sınırı gözetmez. Gün henüz
              birkaç saatliyken ikisi doğal olarak farklı sayı gösterebilir; Transactions'ta gerçekten
              aynı tanımı isteyen "Bugün (UTC takvim günü)" seçeneği var.
            </p>
          )}

          {/* Faz 268-sonrası — kullanıcı geri bildirimi: tarih filtresi
              bölümleri "sönük" görünüyordu, diğer kartlarla AYNI yüzen-
              panel deseni (Card/.glass-panel) içine alındı — tasarım
              bütünlüğü. Dönem sekmeleri (günlük/haftalık/aylık/yıllık) de
              AYNI kartın içine taşındı, ikisi tek bir filtre bloğu. */}
          <Card className="mb-3">
            <div className="flex gap-1 mb-3">
              {PERIOD_TABS.map((t) => (
                <button
                  key={t.key}
                  onClick={() => setPeriodTab(t.key)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                    periodTab === t.key
                      ? "bg-accent text-white border-accent shadow-layer-1"
                      : "bg-surface text-ink border-line shadow-sm hover:bg-surface-soft hover:border-accent/40"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
            <div className="flex items-end gap-2">
              <div>
                <label className="block text-xs text-ink-faint mb-1">Başlangıç</label>
                <Input type="date" value={dateFrom} onChange={setDateFrom} />
              </div>
              <div>
                <label className="block text-xs text-ink-faint mb-1">Bitiş</label>
                <Input type="date" value={dateTo} onChange={setDateTo} />
              </div>
              {(dateFrom || dateTo) && (
                <Button
                  onClick={() => {
                    setDateFrom("");
                    setDateTo("");
                  }}
                >
                  Filtreyi temizle
                </Button>
              )}
            </div>
          </Card>

          <Card padded={false}>
            {(() => {
              let filtered = perf[periodTab].filter((b) => {
                const d = b.period_start.slice(0, 10);
                if (dateFrom && d < dateFrom) return false;
                if (dateTo && d > dateTo) return false;
                return true;
              });
              // Faz 268-sonrası — kullanıcı isteği: günlük tablo sınırsız
              // büyümesin, sabit 15 yerine İÇİNDE BULUNULAN AYIN gün
              // sayısı kadar gösterilsin (28-31 arası, aya göre otomatik
              // — bkz. daysInCurrentMonth). bucket'lar zaten en yeniden
              // en eskiye sıralı geliyor (decision_persistor.py).
              if (periodTab === "daily") filtered = filtered.slice(0, daysInCurrentMonth);
              if (filtered.length === 0) {
                return (
                  <div className="p-5">
                    <EmptyState
                      label={
                        dateFrom || dateTo
                          ? "Seçilen tarih aralığında kapanmış işlem yok."
                          : "Bu dönem için henüz kapanmış işlem yok."
                      }
                    />
                  </div>
                );
              }
              return (
              <div className={`overflow-x-auto ${periodTab === "daily" ? "max-h-96 overflow-y-auto" : ""}`}>
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
                    {filtered.map((b) => (
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
              );
            })()}
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
