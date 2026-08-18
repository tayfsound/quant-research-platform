import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Button, Badge, EmptyState, ErrorNote } from "../components/ui";
import { useCurrency } from "../lib/currency";

const TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d"];

// Kullanıcı bulgusu — TEKRARLANAN "sıfır işlem" şikayeti: backend artık
// max_forward_bars'ı zaman dilimine göre ölçekliyor (backtest/real_
// historical_backtest.py::_default_max_forward_bars, AYNI mantık burada
// da tekrarlanıyor) — 5m/15m gibi hızlı zaman dilimlerinde gerekli
// pencere çok büyüyor (5m'de ~2981 bar). Sabit bir barsCount varsayılanı
// (500) artık 15m/5m'de HER ZAMAN "yetersiz" uyarısını tetiklerdi —
// bars sayısı artık zaman dilimi değişince otomatik öneriliyor.
const TIMEFRAME_TO_MINUTES: Record<string, number> = {
  "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
  "1h": 60, "2h": 120, "4h": 240, "1d": 1440,
};
const DEFAULT_MAX_FORWARD_WINDOW_MINUTES = 10 * 24 * 60; // 10 gün
const BACKTEST_DEFAULT_LOOKBACK = 100; // api/rest/backtest.py'nin kendi varsayılanıyla AYNI

function recommendedBarsCount(timeframe: string): number {
  const tfMinutes = TIMEFRAME_TO_MINUTES[timeframe] ?? 1440;
  const scaledMaxForwardBars = Math.floor(DEFAULT_MAX_FORWARD_WINDOW_MINUTES / tfMinutes);
  const maxForwardBars = Math.max(scaledMaxForwardBars, 200);
  const minRequired = BACKTEST_DEFAULT_LOOKBACK + maxForwardBars + 1;
  return minRequired + 200; // backend'in kendi "en az X+200 önerilir" payı
}

// Faz 268am — kullanıcı bulgusu: "arka planda hali hazırda çalışan bir
// test olduğunda ben bunu göremiyorum." Gerçek sebep: runningReal/
// realStatus sadece bileşenin kendi local state'iydi, hiçbir yerde
// saklanmıyordu — sayfadan ayrılıp dönünce (ya da yenileyince) React
// state sıfırlanıyordu ama celery task arka planda gerçekten çalışmaya
// devam ediyordu; sayfa bundan habersiz "boş" görünüyordu. task_id'yi
// localStorage'a yazıp sayfa her açıldığında kontrol ediyoruz. 3 saatten
// eski bir kayıt (muhtemelen kaybolmuş/çok eski bir task_id) fail-closed
// olarak yok sayılıyor — sonsuza kadar "çalışıyor" görünen bir hayalet
// state bırakmamak için.
const BACKTEST_TASK_STORAGE_KEY = "qrp_backtest_task";
const BACKTEST_TASK_MAX_AGE_MS = 3 * 60 * 60 * 1000;

type BacktestRunSummary = {
  id: string;
  created_at: string;
  symbols: string[];
  total_pnl: number;
  metrics: Record<string, any>;
};

export default function BacktestRuns() {
  const [runs, setRuns] = useState<BacktestRunSummary[]>([]);
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>([]);
  const [timeframe, setTimeframe] = useState("15m");
  // Faz 268-sonrası: kullanıcı bulgusu — 1000 bar varsayılanı, her adımda
  // gerçek bir CognitiveEngine.run() (gerçek embedding dahil) çalıştırdığı
  // için dakikalarca sürüyordu; bu süre boyunca celery worker herhangi bir
  // sebeple yeniden başlarsa (WorkerLostError) çalışan backtest sessizce
  // kayboluyordu.
  //
  // Kullanıcı bulgusu — TEKRARLANAN "sıfır işlem" şikayeti, İKİ ayrı kök
  // nedeni vardı: (1) eski sabit varsayılan (300) backend'in eski sabit
  // lookback(100)+max_forward_bars(200) penceresine sığmıyordu — bu artık
  // baştan "warning" ile tespit ediliyor; (2) max_forward_bars=200 SABİTİ
  // her zaman diliminde AYNI GERÇEK SÜREYİ temsil etmiyordu (15m'de 50
  // saat, 4h'de 33 gün) — hızlı zaman dilimlerinde hiçbir karar kapanma
  // şansı bulamıyordu. İkisi de düzeltildi: max_forward_bars artık zaman
  // dilimine göre ölçekleniyor, barsCount da recommendedBarsCount() ile
  // seçili zaman dilimine göre otomatik öneriliyor (varsayılan: 15m).
  const [barsCount, setBarsCount] = useState(String(recommendedBarsCount("15m")));
  const [runningReal, setRunningReal] = useState(false);
  const [realStatus, setRealStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Faz 268c — kullanıcı bulgusu: localStorage tabanlı takip sadece AYNI
  // tarayıcıda, task'ı başlatan kişi için işe yarıyordu. GET /backtest/
  // active, celery worker'a doğrudan sorup kim/nereden başlattığından
  // bağımsız GERÇEK aktif backtest'leri döndürüyor — sunucu gerçeği.
  const [serverActiveTasks, setServerActiveTasks] = useState<{ task_id: string; args: unknown }[]>([]);
  const [inspectionAvailable, setInspectionAvailable] = useState(true);
  const { format } = useCurrency();

  const load = () => {
    fetch("/api/v1/backtest/runs?limit=20", { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => setRuns(data.runs || []));
  };

  const checkActive = () => {
    fetch("/api/v1/backtest/active", { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => {
        setServerActiveTasks(data.active || []);
        setInspectionAvailable(data.inspection_available !== false);
      })
      .catch(() => {});
  };

  useEffect(() => {
    load();
    checkActive();
    const activeInterval = setInterval(checkActive, 10000);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    return () => clearInterval(activeInterval);
  }, []);

  useEffect(() => {
    fetch("/api/v1/settings/", { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => {
        const list = (data.settings?.watchlist || "").split(",").map((s: string) => s.trim()).filter(Boolean);
        setWatchlist(list);
        if (list.length) setSelectedSymbols([list[0]]);
      });

    const stored = localStorage.getItem(BACKTEST_TASK_STORAGE_KEY);
    if (stored) {
      try {
        const { taskId, startedAt } = JSON.parse(stored);
        if (taskId && Date.now() - startedAt < BACKTEST_TASK_MAX_AGE_MS) {
          setRunningReal(true);
          setRealStatus("...");
          pollTask(taskId);
        } else {
          localStorage.removeItem(BACKTEST_TASK_STORAGE_KEY);
        }
      } catch {
        localStorage.removeItem(BACKTEST_TASK_STORAGE_KEY);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleSymbol = (sym: string) => {
    setSelectedSymbols((prev) => (prev.includes(sym) ? prev.filter((s) => s !== sym) : [...prev, sym]));
  };

  const pollTask = (taskId: string) => {
    const interval = setInterval(() => {
      fetch(`/api/v1/backtest/tasks/${taskId}`, { headers: authHeaders() })
        .then((r) => r.json())
        .then((data) => {
          if (data.status === "SUCCESS") {
            clearInterval(interval);
            localStorage.removeItem(BACKTEST_TASK_STORAGE_KEY);
            setRunningReal(false);
            setRealStatus(null);
            load();
            checkActive();
          } else if (data.status === "FAILURE") {
            clearInterval(interval);
            localStorage.removeItem(BACKTEST_TASK_STORAGE_KEY);
            setRunningReal(false);
            setRealStatus(null);
            setError(`Backtest başarısız: ${data.error || "bilinmeyen hata"}`);
            checkActive();
          } else {
            setRealStatus(data.status);
          }
        })
        .catch(() => {});
    }, 3000);
  };

  const handleRunReal = () => {
    if (selectedSymbols.length === 0) {
      setError("En az bir sembol seçmelisin.");
      return;
    }
    setRunningReal(true);
    setError(null);
    setRealStatus("QUEUED");
    const params = new URLSearchParams({
      symbols: selectedSymbols.join(","),
      timeframe,
      bars_count: barsCount,
    });
    fetch(`/api/v1/backtest/run-real-async?${params.toString()}`, { method: "POST", headers: authHeaders() })
      .then(async (r) => {
        if (!r.ok) {
          const body = await r.json().catch(() => ({}));
          throw new Error(body.detail || `HTTP ${r.status}`);
        }
        return r.json();
      })
      .then((data) => {
        localStorage.setItem(
          BACKTEST_TASK_STORAGE_KEY,
          JSON.stringify({ taskId: data.task_id, startedAt: Date.now() })
        );
        pollTask(data.task_id);
      })
      .catch((e) => {
        setError(String(e.message || e));
        setRunningReal(false);
        setRealStatus(null);
      });
  };

  return (
    <div>
      <PageHeader
        title="Backtests"
        description="Gerçek Binance geçmiş verisiyle, gerçek 9-ajan council'iyle çalışan strateji doğrulaması."
      />

      {error && <ErrorNote>{error}</ErrorNote>}

      {/* Faz 268c — sunucu gerçeği: bu tarayıcıda başlatılmamış olsa bile
          arka planda GERÇEKTEN çalışan bir backtest varsa görünür. */}
      {serverActiveTasks.length > 0 && (
        <div className="mb-6 rounded-xl border border-accent/30 bg-accent-soft p-4">
          <p className="text-sm font-medium text-ink mb-1">
            Arka planda {serverActiveTasks.length} backtest çalışıyor:
          </p>
          {/* Faz 268-sonrası — kullanıcı bulgusu: JSON.stringify(t.args)
              (ör. 49 sembollük bir watchlist dizisi) tek, boşluksuz bir
              satır olarak basılıyordu — konteynerin dışına taşıp
              sonsuza gidiyordu. break-all + overflow-x-auto ile artık
              kutunun içinde sarılıyor/kayıyor. */}
          {serverActiveTasks.map((t, i) => (
            <p key={i} className="text-xs text-ink-soft font-mono break-all whitespace-pre-wrap overflow-x-auto">
              {JSON.stringify(t.args)}
            </p>
          ))}
        </div>
      )}
      {!inspectionAvailable && (
        <p className="text-xs text-ink-faint mb-4">
          Not: worker'a şu an ulaşılamadığı için arka plandaki backtest'ler sorgulanamıyor.
        </p>
      )}

      <Card className="mb-6">
        <h3 className="text-sm font-semibold text-ink mb-3">Gerçek veriyle backtest</h3>
        <p className="text-xs text-ink-soft mb-3">
          Watchlist'ten sembol seç, gerçek Binance geçmiş verisiyle gerçek council karar veriyor, gerçek
          stop/target'a göre çıkış simüle ediliyor. Her bar gerçek bir karar hesapladığı için (embedding
          dahil) dakikalar sürebilir — arka planda çalışır, sayfadan ayrılabilirsin.
        </p>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          {watchlist.map((sym) => (
            <button
              key={sym}
              onClick={() => toggleSymbol(sym)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                selectedSymbols.includes(sym)
                  ? "bg-accent text-white border-accent"
                  : "bg-canvas-soft text-ink-soft border-line hover:bg-surface-soft"
              }`}
            >
              {sym}
            </button>
          ))}
          {watchlist.length > 0 && (
            <span className="flex gap-1 ml-1 pl-2 border-l border-line">
              <button
                onClick={() => setSelectedSymbols(watchlist)}
                className="px-3 py-1.5 rounded-lg text-xs font-medium border border-line text-ink-soft hover:bg-surface-soft transition-colors"
              >
                Tümünü Seç
              </button>
              <button
                onClick={() => setSelectedSymbols([])}
                className="px-3 py-1.5 rounded-lg text-xs font-medium border border-line text-ink-soft hover:bg-surface-soft transition-colors"
              >
                Temizle
              </button>
            </span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <div className="flex gap-1">
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf}
                onClick={() => {
                  setTimeframe(tf);
                  setBarsCount(String(recommendedBarsCount(tf)));
                }}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium border transition-colors ${
                  timeframe === tf
                    ? "bg-accent text-white border-accent"
                    : "bg-canvas-soft text-ink-soft border-line hover:bg-surface-soft"
                }`}
              >
                {tf}
              </button>
            ))}
          </div>
          <label className="text-xs text-ink-soft flex items-center gap-2">
            Geçmiş bar sayısı
            <input
              type="number"
              value={barsCount}
              onChange={(e) => setBarsCount(e.target.value)}
              className="w-24 px-2 py-1 rounded-lg border border-line bg-canvas-soft text-ink text-xs"
            />
          </label>
        </div>
        <Button onClick={handleRunReal} disabled={runningReal}>
          {runningReal ? `Çalışıyor… (${realStatus})` : "Gerçek Veriyle Çalıştır"}
        </Button>
      </Card>

      <h3 className="text-sm font-semibold text-ink-soft uppercase tracking-wide mb-3">Geçmiş Çalıştırmalar</h3>
      {runs.length === 0 ? (
        <EmptyState label="Henüz backtest çalıştırılmadı." />
      ) : (
        <div className="space-y-3">
          {runs.map((r) => {
            const isReal = r.metrics?.mode === "real_historical";
            return (
              <Card key={r.id}>
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <Badge tone={isReal ? "accent" : "neutral"}>{isReal ? "Gerçek veri" : "Sahte veri"}</Badge>
                    <div className="text-sm font-medium text-ink">{r.symbols.join(", ")}</div>
                  </div>
                  <div className={`text-sm font-semibold ${r.total_pnl >= 0 ? "text-rise" : "text-fall"}`}>
                    {format(r.total_pnl)}
                  </div>
                </div>
                <div className="text-xs text-ink-soft mt-2">
                  {isReal ? (
                    <>
                      {r.metrics.timeframe} · {r.metrics.total_trades} işlem · Kazanma oranı{" "}
                      {(r.metrics.overall_win_rate * 100).toFixed(1)}%
                    </>
                  ) : (
                    <>
                      Sharpe {r.metrics?.sharpe_ratio?.toFixed(3)} · Max DD {r.metrics?.max_drawdown?.toFixed(3)}
                    </>
                  )}
                </div>
                {/* Kullanıcı bulgusu — kazanma oranı tek başına, hiçbir
                    barajı görmeden max_forward_bars sonunda terk edilen
                    sinyalleri (çözülmemiş) sessizce dışlıyordu; gerçek bir
                    çalıştırmada üretilen sinyallerin %77'si buydu. Artık
                    her zaman yanında gösteriliyor — hiçbir sayı gizli
                    değil. */}
                {isReal && typeof r.metrics.total_open_positions_never_closed === "number" && (
                  <div className="text-xs text-ink-faint mt-1">
                    {r.metrics.total_open_positions_never_closed > 0 ? (
                      <>
                        + {r.metrics.total_open_positions_never_closed} sinyal hiç stop/hedefe ulaşmadı, çözülmemiş
                        sayılıp kazanma oranından dışlandı ({((r.metrics.overall_resolution_rate ?? 1) * 100).toFixed(0)}%
                        çözülme oranı) — tüm sinyaller üzerinden kazanma oranı{" "}
                        {((r.metrics.overall_win_rate_of_all_signals ?? 0) * 100).toFixed(1)}%
                      </>
                    ) : (
                      "Üretilen tüm sinyaller çözüldü (hiçbiri çözülmemiş bırakılmadı)."
                    )}
                  </div>
                )}
                {/* Kullanıcı bulgusu — tekrarlanan "sıfır işlem" şikayeti:
                    bars_count yapısal olarak yetersizse (lookback +
                    max_forward_bars'ı geçmiyorsa) hiçbir karar kapanma
                    şansı bulamaz — bu artık dashboard'da sessizce
                    kaybolmuyor. */}
                {isReal && r.metrics.warnings?.length > 0 && (
                  <div className="text-xs text-fall mt-1">
                    ⚠ {r.metrics.warnings.join(" ")}
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
