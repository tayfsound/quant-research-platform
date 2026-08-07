import { useEffect, useState } from "react";
import { CycleWebSocket } from "../api/ws_client";
import { Card, PageHeader, Badge, Button, EmptyState } from "../components/ui";
import { useCurrency } from "../lib/currency";

export default function LatestCycle() {
  const [data, setData] = useState<any>(null);
  const [ws] = useState(() => new CycleWebSocket());
  const { format } = useCurrency();

  useEffect(() => {
    ws.connect((newData) => setData(newData));
    return () => ws.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div>
      <PageHeader
        title="Latest Cycle"
        description="Canlı WebSocket üzerinden tetiklenen cycle sonucu."
        action={<Button onClick={() => ws.runCycle()}>Run Cycle</Button>}
      />
      {!data ? (
        <EmptyState label="Veri bekleniyor — bağlantı kurulunca veya Run Cycle'a basınca dolacak." />
      ) : (
        <Card>
          <div className="grid grid-cols-2 gap-y-3 text-sm">
            <div className="text-ink-faint">Direction</div>
            <div><Badge tone={data.direction === "LONG" ? "rise" : data.direction === "SHORT" ? "fall" : "neutral"}>{data.direction}</Badge></div>
            <div className="text-ink-faint">PnL</div>
            <div className={`font-mono ${data.pnl >= 0 ? "text-rise" : "text-fall"}`}>{format(data.pnl)}</div>
            <div className="text-ink-faint">Risk</div>
            <div className="font-mono text-ink">{data.risk_verdict}</div>
          </div>
        </Card>
      )}
    </div>
  );
}
