import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Button, Badge, EmptyState, ErrorNote } from "../components/ui";
import { useCurrency } from "../lib/currency";

const TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d"];

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
  const [barsCount, setBarsCount] = useState("1000");
  const [runningReal, setRunningReal] = useState(false);
  const [realStatus, setRealStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { format } = useCurrency();

  const load = () => {
    fetch("/api/v1/backtest/runs?limit=20", { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => setRuns(data.runs || []));
  };

  useEffect(() => {
    load();
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
          } else if (data.status === "FAILURE") {
            clearInterval(interval);
            localStorage.removeItem(BACKTEST_TASK_STORAGE_KEY);
            setRunningReal(false);
            setRealStatus(null);
            setError(`Backtest başarısız: ${data.error || "bilinmeyen hata"}`);
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
        description="İki ayrı mod: hızlı/deterministik boru hattı testi (sahte fiyat, sadece motorun uçtan uca çalıştığını kanıtlar) ve gerçek Binance geçmiş verisiyle, gerçek 9-ajan council'iyle çalışan asıl strateji doğrulaması."
      />

      {error && <ErrorNote>{error}</ErrorNote>}

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
                onClick={() => setTimeframe(tf)}
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
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
