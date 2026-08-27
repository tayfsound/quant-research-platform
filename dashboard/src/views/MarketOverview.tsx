import { useEffect, useRef, useState } from "react";
import { createChart, CandlestickSeries, ColorType, type IChartApi } from "lightweight-charts";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Badge, EmptyState, Input, Button } from "../components/ui";
import { useCurrency } from "../lib/currency";

const RESOLUTIONS = ["1m", "5m", "15m", "1h", "4h", "1d"];

export default function MarketOverview({
  initialSymbol,
  onSymbolConsumed,
}: {
  initialSymbol?: string | null;
  onSymbolConsumed?: () => void;
} = {}) {
  const [symbol, setSymbol] = useState(initialSymbol || "BTCUSDT");
  const [resolution, setResolution] = useState("1m");
  const [barCount, setBarCount] = useState(0);
  const [orderBook, setOrderBook] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const { format } = useCurrency();
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    // Faz 212: kullanıcı "BTCUSDT'ye tıklayınca dropdown açılmıyor" dedi —
    // burası serbest metin kutusuydu, gerçek bir dropdown hiç yoktu.
    fetch("/api/v1/settings/", { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => {
        const raw = data.settings?.watchlist || "";
        setWatchlist(raw.split(",").map((s: string) => s.trim()).filter(Boolean));
      })
      .catch(() => setWatchlist([]));
  }, []);

  const load = (sym: string, res: string) => {
    setError(null);
    fetch(`/api/v1/market-data/ohlcv?symbol=${sym}&resolution=${res}&limit=300`, { headers: authHeaders() })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => {
        setBarCount(data.bars.length);
        if (!chartRef.current) return;
        const series = (chartRef.current as any)._series;
        if (data.bars.length === 0) {
          series?.setData([]);
          return;
        }
        series?.setData(
          data.bars.map((b: any) => ({
            time: b.time,
            open: b.open,
            high: b.high,
            low: b.low,
            close: b.close,
          }))
        );
        chartRef.current.timeScale().fitContent();
      })
      .catch((e) => setError(String(e.message || e)));

    fetch(`/api/v1/market-data/order-book?symbol=${sym}`, { headers: authHeaders() })
      .then((r) => r.json())
      .then(setOrderBook)
      .catch(() => setOrderBook(null));
  };

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "var(--color-ink-soft)",
        fontFamily: "var(--font-sans)",
      },
      grid: {
        vertLines: { color: "var(--color-line-soft)" },
        horzLines: { color: "var(--color-line-soft)" },
      },
      rightPriceScale: { borderColor: "var(--color-line)" },
      timeScale: { borderColor: "var(--color-line)" },
      height: 420,
      autoSize: true,
    });
    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#3f7d58",
      downColor: "#b3543f",
      borderVisible: false,
      wickUpColor: "#3f7d58",
      wickDownColor: "#b3543f",
    });
    (chart as any)._series = series;
    chartRef.current = chart;

    load(symbol, resolution);

    return () => {
      chart.remove();
      chartRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    load(symbol, resolution);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, resolution]);

  // Kullanıcı bulgusu: Transactions'ta bir işlemin sembolüne tıklayınca
  // (özellikle watchlist dışı Pump-Fade sembollerinde) her zaman gerçek
  // grafik/market bilgisi gösteren bir sayfaya gitmeli — Tokens.tsx'in
  // AYNI initialSymbol/onSymbolConsumed deseni, burada da.
  useEffect(() => {
    if (initialSymbol) {
      setSymbol(initialSymbol);
      onSymbolConsumed?.();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialSymbol]);

  return (
    <div>
      <PageHeader
        title="Market"
        description="Faz 184 Market Data Service'in gerçekten Binance'tan çektiği ve sakladığı OHLCV verisi."
      />

      <Card className="mb-4" padded>
        <div className="flex flex-wrap items-center gap-3">
          <div className="w-40">
            <select
              value={watchlist.includes(symbol) ? symbol : ""}
              onChange={(e) => {
                if (e.target.value) setSymbol(e.target.value);
              }}
              className="w-full px-3 py-2 rounded-lg bg-canvas-soft border border-line text-sm text-ink focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent"
            >
              <option value="" disabled>
                Watchlist'ten seç
              </option>
              {watchlist.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <div className="w-40">
            <Input value={symbol} onChange={setSymbol} placeholder="BTCUSDT" />
          </div>
          <div className="flex gap-1">
            {RESOLUTIONS.map((r) => (
              <button
                key={r}
                onClick={() => setResolution(r)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium ${
                  resolution === r ? "bg-accent text-white" : "bg-canvas-soft text-ink-soft hover:text-ink"
                }`}
              >
                {r}
              </button>
            ))}
          </div>
          <Button variant="secondary" onClick={() => load(symbol, resolution)}>
            Refresh
          </Button>
          <div className="ml-auto">
            <Badge tone={barCount > 0 ? "rise" : "neutral"}>{barCount} bars</Badge>
          </div>
        </div>
      </Card>

      {error && <div className="text-fall text-sm mb-3">{error}</div>}

      <Card padded={false} className="p-2">
        <div ref={containerRef} className="w-full" style={{ minHeight: 420 }} />
      </Card>

      {barCount === 0 && !error && (
        <div className="mt-4">
          <EmptyState label="Henüz bu sembol/çözünürlük için ingest edilmiş veri yok — Market Data Service'in ingest_candles() fonksiyonunu çalıştırın." />
        </div>
      )}

      {orderBook?.available && (
        <div className="grid grid-cols-4 gap-3 mt-4">
          <Card>
            <p className="text-xs text-ink-faint">Best Bid</p>
            <p className="text-lg font-semibold text-rise mt-1">{format(orderBook.best_bid)}</p>
          </Card>
          <Card>
            <p className="text-xs text-ink-faint">Best Ask</p>
            <p className="text-lg font-semibold text-fall mt-1">{format(orderBook.best_ask)}</p>
          </Card>
          <Card>
            <p className="text-xs text-ink-faint">Imbalance</p>
            <p className="text-lg font-semibold mt-1">{(orderBook.imbalance * 100).toFixed(1)}%</p>
          </Card>
          <Card>
            <p className="text-xs text-ink-faint">Spread</p>
            <p className="text-lg font-semibold mt-1">{orderBook.spread_bps.toFixed(1)} bps</p>
          </Card>
        </div>
      )}
    </div>
  );
}
