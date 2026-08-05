import { useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Badge, Button, ErrorNote, EmptyState } from "../components/ui";

function directionTone(direction: string) {
  if (direction === "LONG") return "rise" as const;
  if (direction === "SHORT") return "fall" as const;
  return "neutral" as const;
}

export default function Predictions() {
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const runCycle = () => {
    setLoading(true);
    setError(null);
    fetch("/api/v1/orchestrator/cycle", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ seed: Math.floor(Math.random() * 100000) }),
    })
      .then(async (r) => {
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
        setResult(data);
      })
      .catch((e) => setError(String(e.message || e)))
      .finally(() => setLoading(false));
  };

  return (
    <div>
      <PageHeader
        title="Predictions"
        description="9 ajanlı council'i gerçek bir cycle ile tetikleyip nihai kararı gösterir (CognitiveOrchestrator.run_cycle)."
        action={
          <Button onClick={runCycle} disabled={loading}>
            {loading ? "Running…" : "Run Cycle"}
          </Button>
        }
      />

      {error && <ErrorNote>{error}</ErrorNote>}

      {!result && !error && (
        <EmptyState label="Henüz çalıştırılmadı — gerçek bir council kararı görmek için “Run Cycle”e basın." />
      )}

      {result && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Card>
            <p className="text-xs text-ink-faint uppercase tracking-wide">Direction</p>
            <div className="mt-2">
              <Badge tone={directionTone(result.direction)}>{result.direction}</Badge>
            </div>
            <p className="text-xs text-ink-soft mt-3">Confidence: {(result.confidence * 100).toFixed(0)}%</p>
          </Card>

          <Card>
            <p className="text-xs text-ink-faint uppercase tracking-wide">Risk Verdict</p>
            <div className="mt-2">
              <Badge tone={result.risk_verdict === "approved" ? "rise" : "fall"}>{result.risk_verdict}</Badge>
            </div>
            {result.risk_reasons?.length > 0 && (
              <p className="text-xs text-ink-soft mt-3">{result.risk_reasons.join(", ")}</p>
            )}
          </Card>

          <Card>
            <p className="text-xs text-ink-faint uppercase tracking-wide">Simulated PnL</p>
            <p className={`text-xl font-semibold mt-2 ${result.pnl >= 0 ? "text-rise" : "text-fall"}`}>
              {result.pnl?.toFixed(2)}
            </p>
            <p className="text-xs text-ink-soft mt-1">fee: {result.fee?.toFixed(4)}</p>
          </Card>

          <Card>
            <p className="text-xs text-ink-faint uppercase tracking-wide">Features</p>
            <div className="text-xs text-ink-soft mt-2 space-y-1">
              {result.features && Object.entries(result.features).map(([k, v]) => (
                <div key={k} className="flex justify-between">
                  <span className="capitalize">{k}</span>
                  <span className="font-mono">{typeof v === "number" ? v.toFixed(2) : String(v)}</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
