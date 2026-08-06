import { useEffect, useState } from 'react';
import { Card, PageHeader, Badge, EmptyState } from '../components/ui';
import { useCurrency } from '../lib/currency';

type Token = {
  symbol: string;
  is_crypto: boolean;
  price: number | null;
  direction: string | null;
  confidence: number | null;
  status: string | null;
  market_open: boolean;
};

function directionTone(direction: string | null) {
  if (direction === 'LONG') return 'rise' as const;
  if (direction === 'SHORT') return 'fall' as const;
  return 'neutral' as const;
}

function LivePredictions() {
  const [tokens, setTokens] = useState<Token[] | null>(null);
  const { format } = useCurrency();

  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8000/api/v1/stream/live');
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setTokens(data.tokens || []);
    };
    return () => ws.close();
  }, []);

  return (
    <div>
      <PageHeader
        title="Live Predictions"
        description="Watchlist'teki tüm sembollerin en son gerçek council kararı — 3sn'de bir yenilenir (Faz 215: önceden sadece varsayılan sembolü gösteriyordu, watchlist'e yeni bir sembol eklendiğinde otomatik olarak burada da görünür)."
      />
      {!tokens ? (
        <EmptyState label="Canlı akışa bağlanılıyor…" />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {tokens.map((t) => (
            <Card key={t.symbol}>
              <div className="flex items-center justify-between">
                <span className="font-semibold text-ink tracking-tight">{t.symbol}</span>
                <Badge tone={t.is_crypto ? 'accent' : 'neutral'}>{t.is_crypto ? 'crypto' : 'other'}</Badge>
              </div>
              <p className="text-lg font-semibold text-ink mt-3">{format(t.price, 4)}</p>
              <div className="flex items-center justify-between mt-3">
                {t.market_open ? (
                  <Badge tone={directionTone(t.direction)}>{t.direction ?? 'no data'}</Badge>
                ) : (
                  <Badge tone="neutral">Piyasa kapalı</Badge>
                )}
                {t.confidence != null && (
                  <span className="text-xs text-ink-soft">{(t.confidence * 100).toFixed(0)}% confidence</span>
                )}
              </div>
              {t.status === 'open' && <p className="text-xs text-rise mt-2">açık pozisyon</p>}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
export default LivePredictions;
