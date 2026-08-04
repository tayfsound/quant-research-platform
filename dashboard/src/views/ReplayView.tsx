import { useState } from "react";

export default function ReplayView() {
  const [decisionId, setDecisionId] = useState("");
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleReplay = () => {
    if (!decisionId.trim()) return;
    setLoading(true);
    setError(null);
    fetch(`/api/v1/replay/decision/${decisionId.trim()}`, { method: "POST" })
      .then((r) => r.json())
      .then((data) => {
        if (data.error) setError(data.error);
        setResult(data);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  };

  return (
    <div className="p-4 border rounded">
      <h2 className="text-lg font-bold mb-2">Replay a Decision</h2>
      <div className="flex gap-2 mb-3">
        <input
          value={decisionId}
          onChange={(e) => setDecisionId(e.target.value)}
          placeholder="decision id"
          className="flex-1 px-2 py-1 rounded bg-gray-800 text-sm"
        />
        <button
          onClick={handleReplay}
          disabled={loading}
          className="px-3 py-1 bg-blue-500 text-white rounded text-sm disabled:opacity-50"
        >
          {loading ? "Replaying..." : "Run Replay"}
        </button>
      </div>
      {error && <div className="text-red-400 text-sm">{error}</div>}
      {result && !error && (
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div>Symbol:</div><div className="font-mono">{result.symbol}</div>
          <div>Direction:</div><div className="font-mono">{result.direction}</div>
          <div>Confidence:</div><div className="font-mono">{result.confidence}</div>
          <div>Risk verdict:</div><div className="font-mono">{result.risk_verdict}</div>
          <div>Snapshot restored:</div><div className="font-mono">{String(result.snapshot_restored)}</div>
          <div>Verified (same result):</div>
          <div className={`font-mono ${result.verification?.verified ? "text-green-400" : "text-red-400"}`}>
            {String(result.verification?.verified)}
          </div>
        </div>
      )}
    </div>
  );
}
