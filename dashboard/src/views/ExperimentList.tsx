import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Badge, EmptyState } from "../components/ui";

export default function ExperimentList() {
  const [experiments, setExperiments] = useState<any[]>([]);

  useEffect(() => {
    fetch("/api/v1/experiments/", { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => setExperiments(data.experiments || []));
  }, []);

  return (
    <div>
      <PageHeader title="Experiments" description="Her cognitive cycle'ın git_sha'ya pinlenmiş kaydı." />
      {experiments.length === 0 ? (
        <EmptyState label="Henüz deney kaydı yok." />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {experiments.map((e: any) => (
            <Card key={e.id} className="flex items-center justify-between">
              <div className="text-sm font-mono text-ink-soft">{e.git_sha?.slice(0, 8)}</div>
              <Badge tone="accent">{e.decision_count} decisions</Badge>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
