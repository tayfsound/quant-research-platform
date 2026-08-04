import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";

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
    <div className="p-4 border rounded">
      <h2 className="text-lg font-bold mb-2">Pending Weight Approvals</h2>
      {error && <div className="text-red-400 text-sm mb-2">{error}</div>}
      {approvals.length === 0 ? (
        <div>No pending approvals</div>
      ) : (
        <div className="space-y-2">
          {approvals.map((a) => (
            <div key={a.id} className="flex justify-between items-center p-2 bg-gray-50 rounded">
              <div className="text-sm">
                <div>ID: {a.id.slice(0, 8)}...</div>
                <div>Proposed: {JSON.stringify(a.proposed)}</div>
              </div>
              <button onClick={() => handleApprove(a.id)} className="px-3 py-1 bg-green-500 text-white rounded text-sm">
                Approve
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
