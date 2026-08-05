import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Button, ErrorNote, EmptyState } from "../components/ui";

export default function PendingApprovals() {
  const [approvals, setApprovals] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/v1/weights/pending?limit=10")
      .then((r) => r.json())
      .then((data) => setApprovals(data.pending || []));
  }, []);

  const handleApprove = (id: string) => {
    setError(null);
    // Requires OPERATOR+ role (Sprint 22-24) — weight approval is one of
    // the highest-stakes actions in the system, this is the human-side
    // mirror of "AI can't change risk limits."
    fetch(`/api/v1/weights/${id}/approve`, { method: "POST", headers: authHeaders() })
      .then(async (r) => {
        if (!r.ok) {
          const data = await r.json().catch(() => ({}));
          throw new Error(data.detail || `HTTP ${r.status}`);
        }
        setApprovals((prev) => prev.filter((a) => a.id !== id));
      })
      .catch((e) => setError(String(e.message || e)));
  };

  return (
    <div>
      <PageHeader title="Pending Approvals" description="Ajan ağırlık güncellemeleri — insan onayı zorunlu." />
      {error && <ErrorNote>{error}</ErrorNote>}
      {approvals.length === 0 ? (
        <EmptyState label="Bekleyen onay yok." />
      ) : (
        <div className="space-y-3">
          {approvals.map((a) => (
            <Card key={a.id} className="flex justify-between items-center">
              <div className="text-sm">
                <div className="text-ink font-medium">{a.id.slice(0, 8)}…</div>
                <div className="text-xs text-ink-faint mt-1 font-mono">{JSON.stringify(a.proposed)}</div>
              </div>
              <Button onClick={() => handleApprove(a.id)}>Approve</Button>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
