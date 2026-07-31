import { useEffect, useState } from "react";
import { fetchLatestCycle } from "../api/client";

interface CycleData {
  direction: string;
  pnl: number;
  win: boolean;
  risk_verdict: string;
  memory_size: number;
}

export default function LatestCycle() {
  const [data, setData] = useState<CycleData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchLatestCycle()
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <div className="p-4 text-red-500">Error: {error}</div>;
  if (!data) return <div className="p-4">Loading...</div>;

  return (
    <div className="p-4 border rounded">
      <h2 className="text-lg font-bold mb-2">Latest Cycle</h2>
      <div className="grid grid-cols-2 gap-2 text-sm">
        <div>Direction:</div><div className="font-mono">{data.direction}</div>
        <div>PnL:</div><div className="font-mono">{data.pnl?.toFixed(2)}</div>
        <div>Win:</div><div className="font-mono">{data.win ? "Yes" : "No"}</div>
        <div>Risk:</div><div className="font-mono">{data.risk_verdict}</div>
      </div>
    </div>
  );
}
