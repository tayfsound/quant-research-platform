import { useState } from "react";
import { authHeaders } from "../api/auth";

export default function DecisionExplain() {
  const [decisionId, setDecisionId] = useState("");
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const handleExplain = () => {
    if (!decisionId.trim()) return;
    setError(null);
    setData(null);
    fetch(`/api/v1/decisions/${decisionId.trim()}/explain`, { headers: authHeaders() })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(setData)
      .catch((e) => setError(String(e)));
  };

  return (
    <div className="p-4 border rounded">
      <h2 className="text-lg font-bold mb-2">Explain a Decision</h2>
      <div className="flex gap-2 mb-3">
        <input
          value={decisionId}
          onChange={(e) => setDecisionId(e.target.value)}
          placeholder="decision id"
          className="flex-1 px-2 py-1 rounded bg-gray-800 text-sm"
        />
        <button onClick={handleExplain} className="px-3 py-1 bg-blue-500 text-white rounded text-sm">
          Explain
        </button>
      </div>
      {error && <div className="text-red-400 text-sm">{error}</div>}
      {data && (
        <div className="space-y-3 text-sm">
          <div>{data.symbol} · {data.direction} · size {data.size} · confidence {data.confidence}</div>

          <details open className="bg-gray-900 rounded p-2">
            <summary className="cursor-pointer font-semibold">Agents ({data.chain.agents.length})</summary>
            <pre className="whitespace-pre-wrap text-xs mt-2">{JSON.stringify(data.chain.agents, null, 2)}</pre>
          </details>

          <details className="bg-gray-900 rounded p-2">
            <summary className="cursor-pointer font-semibold">Evidence</summary>
            <pre className="whitespace-pre-wrap text-xs mt-2">{JSON.stringify(data.chain.evidence, null, 2)}</pre>
          </details>

          <details className="bg-gray-900 rounded p-2">
            <summary className="cursor-pointer font-semibold">Belief</summary>
            <pre className="whitespace-pre-wrap text-xs mt-2">{JSON.stringify(data.chain.belief, null, 2)}</pre>
          </details>

          <details className="bg-gray-900 rounded p-2">
            <summary className="cursor-pointer font-semibold">Debate</summary>
            <pre className="whitespace-pre-wrap text-xs mt-2">{JSON.stringify(data.chain.debate, null, 2)}</pre>
          </details>

          <details className="bg-gray-900 rounded p-2">
            <summary className="cursor-pointer font-semibold">Risk</summary>
            <pre className="whitespace-pre-wrap text-xs mt-2">{JSON.stringify(data.chain.risk, null, 2)}</pre>
          </details>

          <details className="bg-gray-900 rounded p-2">
            <summary className="cursor-pointer font-semibold">Weight snapshot</summary>
            <pre className="whitespace-pre-wrap text-xs mt-2">{JSON.stringify(data.chain.weight_snapshot, null, 2)}</pre>
          </details>

          <details className="bg-gray-900 rounded p-2">
            <summary className="cursor-pointer font-semibold">Outcome</summary>
            <pre className="whitespace-pre-wrap text-xs mt-2">{JSON.stringify(data.chain.outcome, null, 2)}</pre>
          </details>
        </div>
      )}
    </div>
  );
}
