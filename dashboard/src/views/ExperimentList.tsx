import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Badge, EmptyState } from "../components/ui";

export default function ExperimentList() {
  const [experiments, setExperiments] = useState<any[]>([]);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/v1/experiments/", { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => setExperiments(data.experiments || []));
  }, []);

  const copyId = (id: string) => {
    navigator.clipboard.writeText(id).then(() => {
      setCopiedId(id);
      setTimeout(() => setCopiedId((cur) => (cur === id ? null : cur)), 1500);
    });
  };

  return (
    <div>
      <PageHeader
        title="Experiments"
        description="Her cognitive cycle'ın git_sha'ya pinlenmiş kaydı. Bir decision id'ye tıklayıp kopyalayarak Replay sekmesinde kullanabilirsin."
      />
      {experiments.length === 0 ? (
        <EmptyState label="Henüz deney kaydı yok." />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {experiments.map((e: any) => (
            <Card key={e.id}>
              <div className="flex items-center justify-between mb-2">
                <div className="text-sm font-mono text-ink-soft">{e.git_sha?.slice(0, 8)}</div>
                <Badge tone="accent">{e.decision_count} decisions</Badge>
              </div>
              <div className="text-xs text-ink-faint mb-2">{new Date(e.timestamp).toLocaleString()}</div>
              {e.decision_ids && e.decision_ids.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {e.decision_ids.map((id: string) => (
                    <button
                      key={id}
                      onClick={() => copyId(id)}
                      title="Kopyala — Replay sekmesine yapıştır"
                      className="text-[11px] font-mono px-2 py-1 rounded bg-canvas-soft hover:bg-surface-soft text-ink-soft border border-line transition-colors"
                    >
                      {copiedId === id ? "kopyalandı ✓" : id.slice(0, 8)}
                    </button>
                  ))}
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
