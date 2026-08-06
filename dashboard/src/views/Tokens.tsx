import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Badge, Button, ErrorNote, EmptyState, Spinner } from "../components/ui";

type Token = {
  symbol: string;
  is_crypto: boolean;
  price: number | null;
  direction: string | null;
  confidence: number | null;
  size: number | null;
  status: string | null;
  updated_at: string | null;
  market_open: boolean;
};

type Decision = {
  id: string;
  timestamp: string;
  direction: string;
  confidence: number | null;
  size: number | null;
  status: string;
  pnl: number | null;
  entry_price: number | null;
  exit_price: number | null;
  opened_at: string | null;
  closed_at: string | null;
  exit_reason: string | null;
};

type TokenDetail = {
  symbol: string;
  is_crypto: boolean;
  price: number | null;
  order_book: {
    best_bid: number;
    best_ask: number;
    imbalance: number;
    spread_bps: number;
    time: string;
  } | null;
  decisions: Decision[];
};

function directionTone(direction: string | null) {
  if (direction === "LONG") return "rise" as const;
  if (direction === "SHORT") return "fall" as const;
  return "neutral" as const;
}

function TokenList({ tokens, onSelect }: { tokens: Token[]; onSelect: (symbol: string) => void }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {tokens.map((t) => (
        <button key={t.symbol} onClick={() => onSelect(t.symbol)} className="text-left">
          <Card className="hover:shadow-layer-2 transition-shadow h-full">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-ink tracking-tight">{t.symbol}</span>
              <Badge tone={t.is_crypto ? "accent" : "neutral"}>{t.is_crypto ? "crypto" : "other"}</Badge>
            </div>
            <p className="text-lg font-semibold text-ink mt-3">
              {t.price != null ? t.price.toLocaleString(undefined, { maximumFractionDigits: 4 }) : "—"}
            </p>
            <div className="flex items-center justify-between mt-3">
              {t.market_open ? (
                <Badge tone={directionTone(t.direction)}>{t.direction ?? "no data"}</Badge>
              ) : (
                <Badge tone="neutral">Piyasa kapalı</Badge>
              )}
              {t.confidence != null && (
                <span className="text-xs text-ink-soft">{(t.confidence * 100).toFixed(0)}% confidence</span>
              )}
            </div>
            {t.status === "open" && (
              <p className="text-xs text-rise mt-2">açık pozisyon · {t.size?.toFixed(4)}</p>
            )}
          </Card>
        </button>
      ))}
    </div>
  );
}

function TokenDetailView({ symbol, onBack }: { symbol: string; onBack: () => void }) {
  const [detail, setDetail] = useState<TokenDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setError(null);
    fetch(`/api/v1/tokens/${symbol}`, { headers: authHeaders() })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(setDetail)
      .catch((e) => setError(String(e.message || e)));
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 15000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol]);

  return (
    <div>
      <PageHeader
        title={symbol}
        description="Bu sembol için son council kararları, güncel fiyat ve order book."
        action={
          <Button variant="secondary" onClick={onBack}>
            ← Tokens'a dön
          </Button>
        }
      />

      {error && <ErrorNote>{error}</ErrorNote>}

      {!detail && !error && (
        <div className="flex justify-center py-12">
          <Spinner />
        </div>
      )}

      {detail && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
            <Card>
              <p className="text-xs text-ink-faint uppercase tracking-wide">Fiyat</p>
              <p className="text-xl font-semibold mt-2">
                {detail.price != null ? detail.price.toLocaleString(undefined, { maximumFractionDigits: 4 }) : "—"}
              </p>
            </Card>
            {detail.order_book ? (
              <>
                <Card>
                  <p className="text-xs text-ink-faint uppercase tracking-wide">Best Bid / Ask</p>
                  <p className="text-sm font-semibold mt-2">
                    <span className="text-rise">{detail.order_book.best_bid.toFixed(2)}</span>
                    {" / "}
                    <span className="text-fall">{detail.order_book.best_ask.toFixed(2)}</span>
                  </p>
                </Card>
                <Card>
                  <p className="text-xs text-ink-faint uppercase tracking-wide">Imbalance</p>
                  <p className="text-xl font-semibold mt-2">{(detail.order_book.imbalance * 100).toFixed(1)}%</p>
                </Card>
                <Card>
                  <p className="text-xs text-ink-faint uppercase tracking-wide">Spread</p>
                  <p className="text-xl font-semibold mt-2">{detail.order_book.spread_bps.toFixed(1)} bps</p>
                </Card>
              </>
            ) : (
              <Card className="md:col-span-3">
                <p className="text-xs text-ink-faint uppercase tracking-wide">Order Book</p>
                <p className="text-sm text-ink-soft mt-2">
                  {detail.is_crypto ? "Henüz order book verisi ingest edilmedi." : "Bu sembol kripto olmadığı için order book yok."}
                </p>
              </Card>
            )}
          </div>

          <Card padded={false}>
            <div className="px-5 py-4 border-b border-line-soft">
              <p className="text-sm font-semibold text-ink">Son kararlar</p>
            </div>
            {detail.decisions.length === 0 ? (
              <div className="p-5">
                <EmptyState label="Bu sembol için henüz kaydedilmiş bir council kararı yok." />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-ink-faint uppercase tracking-wide border-b border-line-soft">
                      <th className="px-5 py-2 font-medium">Yön</th>
                      <th className="px-5 py-2 font-medium">Confidence</th>
                      <th className="px-5 py-2 font-medium">Büyüklük</th>
                      <th className="px-5 py-2 font-medium">Durum</th>
                      <th className="px-5 py-2 font-medium">Giriş</th>
                      <th className="px-5 py-2 font-medium">Çıkış</th>
                      <th className="px-5 py-2 font-medium">Sebep</th>
                      <th className="px-5 py-2 font-medium">PnL</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.decisions.map((d) => (
                      <tr key={d.id} className="border-b border-line-soft last:border-0">
                        <td className="px-5 py-2.5">
                          <Badge tone={directionTone(d.direction)}>{d.direction}</Badge>
                        </td>
                        <td className="px-5 py-2.5 text-ink-soft">
                          {d.confidence != null ? `${(d.confidence * 100).toFixed(0)}%` : "—"}
                        </td>
                        <td className="px-5 py-2.5 text-ink-soft">{d.size != null ? d.size.toFixed(4) : "—"}</td>
                        <td className="px-5 py-2.5">
                          <Badge tone={d.status === "open" ? "accent" : d.status === "closed" ? "neutral" : "neutral"}>
                            {d.status}
                          </Badge>
                        </td>
                        <td className="px-5 py-2.5 text-ink-soft text-xs">
                          {d.opened_at ? (
                            <>
                              <div>{new Date(d.opened_at).toLocaleString()}</div>
                              {d.entry_price != null && <div className="font-mono">{d.entry_price.toFixed(4)}</div>}
                            </>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="px-5 py-2.5 text-ink-soft text-xs">
                          {d.closed_at ? (
                            <>
                              <div>{new Date(d.closed_at).toLocaleString()}</div>
                              {d.exit_price != null && <div className="font-mono">{d.exit_price.toFixed(4)}</div>}
                            </>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="px-5 py-2.5 text-ink-soft text-xs">{d.exit_reason ?? "—"}</td>
                        <td className={`px-5 py-2.5 font-medium ${d.pnl != null && d.pnl >= 0 ? "text-rise" : d.pnl != null ? "text-fall" : "text-ink-faint"}`}>
                          {d.pnl != null ? d.pnl.toFixed(2) : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}

export default function Tokens() {
  const [tokens, setTokens] = useState<Token[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    fetch("/api/v1/tokens/", { headers: authHeaders() })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => setTokens(data.tokens || []))
      .catch((e) => setError(String(e.message || e)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 15000);
    return () => clearInterval(interval);
  }, []);

  if (selected) {
    return <TokenDetailView symbol={selected} onBack={() => setSelected(null)} />;
  }

  return (
    <div>
      <PageHeader
        title="Tokens"
        description="AI'ın izlediği watchlist'in tamamı — her karta tıklayınca sembolün detayına gidersin."
      />

      {error && <ErrorNote>{error}</ErrorNote>}

      {loading && (
        <div className="flex justify-center py-12">
          <Spinner />
        </div>
      )}

      {!loading && tokens.length === 0 && !error && (
        <EmptyState label="Watchlist boş görünüyor — Settings'ten watchlist'i kontrol edin." />
      )}

      {!loading && tokens.length > 0 && <TokenList tokens={tokens} onSelect={setSelected} />}
    </div>
  );
}
