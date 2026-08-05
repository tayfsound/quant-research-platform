import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Button, EmptyState } from "../components/ui";

export default function BacktestRuns() {
  const [runs, setRuns] = useState<any[]>([]);
  const [running, setRunning] = useState(false);

  const load = () => {
    fetch("/api/v1/backtest/runs?limit=20", { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => setRuns(data.runs || []));
  };

  useEffect(() => {
    load();
  }, []);

  const handleRun = () => {
    setRunning(true);
    fetch("/api/v1/backtest/run?symbols=BTCUSDT&bars=200", { method: "POST", headers: authHeaders() })
      .then(() => load())
      .finally(() => setRunning(false));
  };

  return (
    <div>
      <PageHeader
        title="Backtests"
        description="Vektörize motor + gerçek CognitiveEngine ile deterministik geçmiş test."
        action={
          <Button onClick={handleRun} disabled={running}>
            {running ? "Running…" : "Run Backtest"}
          </Button>
        }
      />
      {runs.length === 0 ? (
        <EmptyState label="Henüz backtest çalıştırılmadı." />
      ) : (
        <div className="space-y-3">
          {runs.map((r: any) => (
            <Card key={r.id}>
              <div className="flex items-center justify-between">
                <div className="text-sm font-medium text-ink">{r.symbols.join(", ")}</div>
                <div className={`text-sm font-semibold ${r.total_pnl >= 0 ? "text-rise" : "text-fall"}`}>
                  {r.total_pnl?.toFixed(2)}
                </div>
              </div>
              <div className="text-xs text-ink-soft mt-2">
                Sharpe {r.metrics?.sharpe_ratio?.toFixed(3)} · Max DD {r.metrics?.max_drawdown?.toFixed(3)}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
