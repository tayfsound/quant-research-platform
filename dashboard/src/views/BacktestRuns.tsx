import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";

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
    <div className="p-4 border rounded">
      <div className="flex justify-between items-center mb-2">
        <h2 className="text-lg font-bold">Backtest Runs</h2>
        <button
          onClick={handleRun}
          disabled={running}
          className="px-3 py-1 bg-blue-500 text-white rounded text-sm disabled:opacity-50"
        >
          {running ? "Running..." : "Run Backtest"}
        </button>
      </div>
      {runs.length === 0 ? (
        <div>No backtest runs yet</div>
      ) : (
        <div className="space-y-2">
          {runs.map((r: any) => (
            <div key={r.id} className="text-sm p-2 bg-gray-50 rounded">
              <div>Symbols: {r.symbols.join(", ")}</div>
              <div>Total PnL: {r.total_pnl?.toFixed(2)}</div>
              <div>Sharpe: {r.metrics?.sharpe_ratio?.toFixed(3)} · Max DD: {r.metrics?.max_drawdown?.toFixed(3)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
