import { useEffect, useState } from "react";
import { CycleWebSocket } from "../api/ws_client";

export default function LatestCycle() {
  const [data, setData] = useState<any>(null);
  const [ws] = useState(() => new CycleWebSocket());

  useEffect(() => {
    ws.connect((newData) => setData(newData));
    return () => ws.disconnect();
  }, []);

  return (
    <div className="p-4 border rounded">
      <h2 className="text-lg font-bold mb-2">Latest Cycle (Live)</h2>
      <button onClick={() => ws.runCycle()} className="mb-2 px-3 py-1 bg-blue-500 text-white rounded">
        Run Cycle
      </button>
      {data ? (
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div>Direction:</div><div className="font-mono">{data.direction}</div>
          <div>PnL:</div><div className="font-mono">{data.pnl?.toFixed(2)}</div>
          <div>Risk:</div><div className="font-mono">{data.risk_verdict}</div>
        </div>
      ) : (
        <div>Waiting for data...</div>
      )}
    </div>
  );
}
