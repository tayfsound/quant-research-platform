import { useState } from 'react';
import { authHeaders } from '../api/auth';

function AIReasoning() {
  const [explanation, setExplanation] = useState(null);
  const [loading, setLoading] = useState(false);

  const testRequest = async () => {
    setLoading(true);
    const res = await fetch('http://localhost:8000/api/v1/reasoning/explain', {
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
    setExplanation(data);
    setLoading(false);
  };

  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">AI Reasoning (LLM)</h2>
      <button
        onClick={testRequest}
        disabled={loading}
        className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded mb-4"
      >
        {loading ? 'Thinking...' : 'Test LLM Reasoning'}
      </button>
      {explanation && (
        <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
          <p className="text-green-400 font-semibold">Explanation:</p>
          <p className="text-gray-200 mt-1">{explanation.explanation}</p>
          {explanation.risks && explanation.risks.length > 0 && (
            <div className="mt-3">
              <p className="text-red-400 font-semibold">Risks:</p>
              <ul className="list-disc list-inside text-gray-300">
                {explanation.risks.map((r: string, i: number) => <li key={i}>{r}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
export default AIReasoning;
