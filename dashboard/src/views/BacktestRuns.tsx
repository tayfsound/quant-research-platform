import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Button, Badge, EmptyState, ErrorNote } from "../components/ui";
import { useCurrency } from "../lib/currency";

const TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d"];

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
  const [runningMock, setRunningMock] = useState(false);
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
  }, []);

  const toggleSymbol = (sym: string) => {
    setSelectedSymbols((prev) => (prev.includes(sym) ? prev.filter((s) => s !== sym) : [...prev, sym]));
  };

  const handleRunMock = () => {
    setRunningMock(true);
    setError(null);
    fetch("/api/v1/backtest/run?symbols=BTCUSDT&bars=200", { method: "POST", headers: authHeaders() })
      .then(() => load())
      .catch((e) => setError(String(e.message || e)))
      .finally(() => setRunningMock(false));
  };

  const pollTask = (taskId: string) => {
    const interval = setInterval(() => {
      fetch(`/api/v1/backtest/tasks/${taskId}`, { headers: authHeaders() })
        .then((r) => r.json())
        .then((data) => {
          if (data.status === "SUCCESS") {
            clearInterval(interval);
            setRunningReal(false);
            setRealStatus(null);
            load();
          } else if (data.status === "FAILURE") {
            clearInterval(interval);
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
      .then((data) => pollTask(data.task_id))
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
        <div className="flex flex-wrap gap-2 mb-3">
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

      <Card className="mb-6">
        <h3 className="text-sm font-semibold text-ink mb-1">Hızlı boru hattı testi (sahte veri)</h3>
        <p className="text-xs text-ink-soft mb-3">
          Deterministik, sahte fiyat verisiyle — sadece motorun (council → risk → fusion → persist) uçtan
          uca çalıştığını doğrular. Strateji kalitesi hakkında hiçbir şey söylemez.
        </p>
        <Button variant="secondary" onClick={handleRunMock} disabled={runningMock}>
          {runningMock ? "Çalışıyor…" : "Hızlı Test Çalıştır"}
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
