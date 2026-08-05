import { useState } from 'react';
import { authHeaders } from '../api/auth';
import { Card, PageHeader, Button, ErrorNote, EmptyState } from '../components/ui';

function AIReasoning() {
  const [explanation, setExplanation] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const testRequest = async () => {
    setLoading(true);
    setError(null);
    setExplanation(null);
    try {
      const res = await fetch('/api/v1/reasoning/explain', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', ...authHeaders()},
        body: JSON.stringify({
          symbol: "BTCUSDT",
          direction: "LONG",
          confidence: 0.82,
          agent_votes: {
            trend_agent: {direction: "LONG", confidence: 0.85},
            momentum_agent: {direction: "LONG", confidence: 0.78}
          },
          market_snapshot: {price: 50250, rsi_14: 32.5, macd: -125, regime: "sideways"},
          onchain_signals: {whale_accumulation: true, exchange_outflow_24h: 12500},
          macro_context: {next_fomc: "2026-07-30", fear_greed_index: 65}
        })
      });
      const data = await res.json();
      if (!res.ok) {
        setError(`HTTP ${res.status}: ${data.detail || JSON.stringify(data)}`);
        return;
      }
      setExplanation(data);
    } catch (e: any) {
      setError(`Network error: ${e.message || e}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="AI Reasoning"
        description="Yerel Ollama üzerinden LLM'in gerçek bir kararı Türkçe açıklaması."
        action={
          <Button onClick={testRequest} disabled={loading}>
            {loading ? 'Düşünüyor…' : 'Test LLM Reasoning'}
          </Button>
        }
      />
      {error && <ErrorNote>{error}</ErrorNote>}
      {!explanation && !error && (
        <EmptyState label="Henüz çalıştırılmadı — gerçek bir LLM açıklaması görmek için butona basın (birkaç saniye sürer)." />
      )}
      {explanation && (
        <Card>
          <p className="text-rise font-semibold text-sm mb-1">Explanation</p>
          <p className="text-ink text-sm leading-relaxed">{explanation.explanation}</p>
          {explanation.risks && explanation.risks.length > 0 && (
            <div className="mt-4">
              <p className="text-fall font-semibold text-sm mb-1">Risks</p>
              <ul className="list-disc list-inside text-ink-soft text-sm space-y-0.5">
                {explanation.risks.map((r: string, i: number) => <li key={i}>{r}</li>)}
              </ul>
            </div>
          )}
          {explanation.confidence_comment && (
            <p className="text-xs text-ink-faint mt-4 pt-3 border-t border-line-soft">{explanation.confidence_comment}</p>
          )}
        </Card>
      )}
    </div>
  );
}
export default AIReasoning;
