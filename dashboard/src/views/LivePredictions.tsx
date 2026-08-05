import { useEffect, useState } from 'react';
import { Card, PageHeader, Badge, EmptyState } from '../components/ui';

function LivePredictions() {
  const [prediction, setPrediction] = useState<any>(null);

  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8000/api/v1/stream/live');
    ws.onmessage = (event) => {
      setPrediction(JSON.parse(event.data));
    };
    return () => ws.close();
  }, []);

  const direction = prediction?.direction === 1 ? 'LONG' : prediction?.direction === -1 ? 'SHORT' : 'NEUTRAL';
  const tone = prediction?.direction === 1 ? 'rise' : prediction?.direction === -1 ? 'fall' : 'neutral';

  return (
    <div>
      <PageHeader
        title="Live Predictions"
        description="Her 2 saniyede bir gerçek bir CognitiveOrchestrator cycle'ı çalıştırılır."
      />
      {!prediction ? (
        <EmptyState label="Canlı akışa bağlanılıyor…" />
      ) : (
        <Card>
          <div className="flex flex-wrap gap-8 items-center">
            <div>
              <p className="text-xs text-ink-faint uppercase tracking-wide">Symbol</p>
              <p className="text-lg font-semibold text-ink mt-1">{prediction.symbol}</p>
            </div>
            <div>
              <p className="text-xs text-ink-faint uppercase tracking-wide">Direction</p>
              <div className="mt-1"><Badge tone={tone as any}>{direction}</Badge></div>
            </div>
            <div>
              <p className="text-xs text-ink-faint uppercase tracking-wide">Confidence</p>
              <p className="text-lg font-semibold text-ink mt-1">{(prediction.confidence * 100).toFixed(0)}%</p>
            </div>
          </div>
          <div className="mt-5 pt-4 border-t border-line-soft flex gap-6 text-sm text-ink-soft">
            <span>RSI: <span className="font-mono text-ink">{prediction.features?.rsi}</span></span>
            <span>MACD: <span className="font-mono text-ink">{prediction.features?.macd}</span></span>
          </div>
        </Card>
      )}
    </div>
  );
}
export default LivePredictions;
