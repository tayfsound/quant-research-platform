import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Button, Badge, ErrorNote, EmptyState } from "../components/ui";

type Approval = {
  id: string;
  timestamp: string | null;
  proposed: Record<string, number>;
  previous: Record<string, number>;
  max_delta: number;
  status: string;
};

// Faz 224: kullanıcı bulgusu — "Approval a gelen onay sorularının formatı
// çok dağınık kod gibi görünüyor... yatay scrolling felan yapmadan
// onaylayamıyorum çok özensiz." Eskiden JSON.stringify(a.proposed) tek
// satırlık font-mono metin olarak basılıyordu — hem önceki değeri hiç
// göstermiyordu hem de yatay taşıyordu. Artık her ajan domain'i için
// önceki/yeni/değişim ayrı satırlarda, en büyük değişiklik en üstte.
function WeightDiffRows({ proposed, previous }: { proposed: Record<string, number>; previous: Record<string, number> }) {
  const domains = Array.from(new Set([...Object.keys(previous), ...Object.keys(proposed)]));
  const rows = domains
    .map((domain) => {
      const before = previous[domain] ?? 0;
      const after = proposed[domain] ?? 0;
      return { domain, before, after, delta: after - before };
    })
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-ink-faint uppercase tracking-wide border-b border-line-soft">
            <th className="py-1.5 pr-4 font-medium">Ajan</th>
            <th className="py-1.5 pr-4 font-medium">Önceki</th>
            <th className="py-1.5 pr-4 font-medium">Yeni</th>
            <th className="py-1.5 pr-4 font-medium">Değişim</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.domain} className="border-b border-line-soft last:border-0">
              <td className="py-1.5 pr-4 text-ink font-medium">{r.domain}</td>
              <td className="py-1.5 pr-4 text-ink-soft font-mono">{r.before.toFixed(3)}</td>
              <td className="py-1.5 pr-4 text-ink font-mono">{r.after.toFixed(3)}</td>
              <td className={`py-1.5 pr-4 font-mono ${r.delta > 0 ? "text-rise" : r.delta < 0 ? "text-fall" : "text-ink-faint"}`}>
                {r.delta > 0 ? "+" : ""}
                {r.delta.toFixed(3)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function PendingApprovals() {
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = () => {
    fetch("/api/v1/weights/pending?limit=10")
      .then((r) => r.json())
      .then((data) => setApprovals(data.pending || []));
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 15000);
    return () => clearInterval(interval);
  }, []);

  const decide = (id: string, action: "approve" | "reject") => {
    setError(null);
    setBusyId(id);
    // OPERATOR+ rolü gerektirir — ağırlık onayı sistemdeki en kritik
    // insan-müdahale noktalarından biri.
    fetch(`/api/v1/weights/${id}/${action}`, { method: "POST", headers: authHeaders() })
      .then(async (r) => {
        if (!r.ok) {
          const data = await r.json().catch(() => ({}));
          throw new Error(data.detail || `HTTP ${r.status}`);
        }
        setApprovals((prev) => prev.filter((a) => a.id !== id));
      })
      .catch((e) => setError(String(e.message || e)))
      .finally(() => setBusyId(null));
  };

  return (
    <div>
      <PageHeader
        title="Pending Approvals"
        description="Ajan ağırlık güncellemeleri — büyük bir değişiklik (max_delta'yı aşan) önerildiğinde otomatik uygulanmaz, insan onayı bekler."
      />
      {error && <ErrorNote>{error}</ErrorNote>}
      {approvals.length === 0 ? (
        <EmptyState label="Bekleyen onay yok." />
      ) : (
        <div className="space-y-4">
          {approvals.map((a) => (
            <Card key={a.id}>
              <div className="flex items-start justify-between gap-4 mb-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-ink font-medium font-mono text-xs">{a.id.slice(0, 8)}…</span>
                    <Badge tone="neutral">izin verilen max değişim: ±{a.max_delta.toFixed(2)}</Badge>
                  </div>
                  {a.timestamp && (
                    <p className="text-xs text-ink-faint mt-1">{new Date(a.timestamp).toLocaleString()}</p>
                  )}
                </div>
                <div className="flex gap-2 shrink-0">
                  <Button
                    variant="danger"
                    disabled={busyId === a.id}
                    onClick={() => decide(a.id, "reject")}
                  >
                    Reddet
                  </Button>
                  <Button disabled={busyId === a.id} onClick={() => decide(a.id, "approve")}>
                    Onayla
                  </Button>
                </div>
              </div>
              <WeightDiffRows proposed={a.proposed} previous={a.previous} />
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
