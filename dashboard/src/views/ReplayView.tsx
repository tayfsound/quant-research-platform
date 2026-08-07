import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Input, Button, ErrorNote, Badge } from "../components/ui";

export default function ReplayView({ initialId }: { initialId?: string | null }) {
  const [decisionId, setDecisionId] = useState(initialId || "");
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleReplay = (idOverride?: string) => {
    const id = (idOverride ?? decisionId).trim();
    if (!id) return;
    setLoading(true);
    setError(null);
    fetch(`/api/v1/replay/decision/${id}`, { method: "POST", headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => {
        if (data.error) setError(data.error);
        setResult(data);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  };

  // Faz 252: kullanıcı bulgusu — Replay sayfası bir decision ID istiyordu
  // ama panelde hiçbir yerde ID gösterilmiyordu, kopyalanacak bir kaynak
  // yoktu. Artık Transactions sayfasındaki her kapanmış işlemin "Replay"
  // butonu buraya doğrudan ID ile yönlendirip otomatik çalıştırıyor.
  useEffect(() => {
    if (initialId) {
      setDecisionId(initialId);
      handleReplay(initialId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialId]);

  return (
    <div>
      <PageHeader title="Replay" description="Bir kararı deterministik olarak yeniden çalıştırıp aynı sonucu doğrular." />
      <Card className="mb-4">
        <div className="flex gap-2">
          <Input value={decisionId} onChange={setDecisionId} placeholder="decision id" />
          <Button onClick={() => handleReplay()} disabled={loading}>
            {loading ? "Replaying…" : "Run Replay"}
          </Button>
        </div>
      </Card>
      {error && <ErrorNote>{error}</ErrorNote>}
      {result && !error && (
        <Card>
          <div className="grid grid-cols-2 gap-y-3 text-sm">
            <div className="text-ink-faint">Symbol</div><div className="font-mono text-ink">{result.symbol}</div>
            <div className="text-ink-faint">Direction</div><div className="font-mono text-ink">{result.direction}</div>
            <div className="text-ink-faint">Confidence</div><div className="font-mono text-ink">{result.confidence}</div>
            <div className="text-ink-faint">Risk verdict</div><div className="font-mono text-ink">{result.risk_verdict}</div>
            <div className="text-ink-faint">Snapshot restored</div><div className="font-mono text-ink">{String(result.snapshot_restored)}</div>
            <div className="text-ink-faint">Verified</div>
            <div><Badge tone={result.verification?.verified ? "rise" : "fall"}>{String(result.verification?.verified)}</Badge></div>
          </div>
        </Card>
      )}
    </div>
  );
}
