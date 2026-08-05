import { useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Input, Button, ErrorNote, Badge, CodeBlock } from "../components/ui";

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

  const sections: [string, string][] = [
    ["agents", "Agents"],
    ["evidence", "Evidence"],
    ["belief", "Belief"],
    ["debate", "Debate"],
    ["risk", "Risk"],
    ["weight_snapshot", "Weight snapshot"],
    ["outcome", "Outcome"],
  ];

  return (
    <div>
      <PageHeader title="Explain" description="Bir kararın tüm zincirini (agent→evidence→belief→debate→risk→weight→outcome) gösterir." />
      <Card className="mb-4">
        <div className="flex gap-2">
          <Input value={decisionId} onChange={setDecisionId} placeholder="decision id" />
          <Button onClick={handleExplain}>Explain</Button>
        </div>
      </Card>
      {error && <ErrorNote>{error}</ErrorNote>}
      {data && (
        <div className="space-y-3">
          <Card>
            <div className="flex flex-wrap gap-4 items-center text-sm">
              <span className="font-medium text-ink">{data.symbol}</span>
              <Badge tone={data.direction === "LONG" ? "rise" : data.direction === "SHORT" ? "fall" : "neutral"}>{data.direction}</Badge>
              <span className="text-ink-soft">size {data.size}</span>
              <span className="text-ink-soft">confidence {data.confidence}</span>
            </div>
          </Card>
          {sections.map(([key, label]) => (
            <details key={key} className="group bg-surface border border-line rounded-xl shadow-layer-1 overflow-hidden">
              <summary className="cursor-pointer select-none px-5 py-3 text-sm font-medium text-ink hover:bg-canvas-soft flex items-center justify-between">
                {label}
                {key === "agents" && Array.isArray(data.chain?.agents) && (
                  <span className="text-xs text-ink-faint">{data.chain.agents.length}</span>
                )}
              </summary>
              <div className="px-5 pb-4">
                <CodeBlock>{JSON.stringify(data.chain?.[key], null, 2)}</CodeBlock>
              </div>
            </details>
          ))}
        </div>
      )}
    </div>
  );
}
