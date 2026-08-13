import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Badge } from "../components/ui";

export default function Strategies() {
  const [agents, setAgents] = useState<any[]>([]);
  const [critics, setCritics] = useState<any[]>([]);

  useEffect(() => {
    fetch("/api/v1/agents/", { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => {
        setAgents(data.agents || []);
        setCritics(data.critics || []);
      });
  }, []);

  return (
    <div>
      <PageHeader
        title="Agents"
        description="Ajanlar, kendi uzmanlık alanlarına göre belirli görevleri yerine getiren ya da içgörü sağlayan yapay zeka destekli modüllerdir. Süreçleri otomatikleştirmek, veri analiz etmek veya karar almaya yardımcı olmak için kullanılırlar."
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        {agents.map((a) => (
          <Card key={a.domain}>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-semibold text-ink capitalize">{a.domain.replaceAll("_", " ")}</h3>
              <Badge tone="accent">vote</Badge>
            </div>
            <p className="text-xs text-ink-soft leading-relaxed">{a.description}</p>
          </Card>
        ))}
      </div>

      <h3 className="text-sm font-semibold text-ink-soft uppercase tracking-wide mb-3">Critics &amp; annotators</h3>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {critics.map((c) => (
          <Card key={c.domain}>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-semibold text-ink capitalize">{c.domain.replaceAll("_", " ")}</h3>
              <Badge tone="warn">{c.role}</Badge>
            </div>
            <p className="text-xs text-ink-soft leading-relaxed">{c.description}</p>
          </Card>
        ))}
      </div>
    </div>
  );
}
