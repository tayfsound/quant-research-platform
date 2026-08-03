import { useEffect, useState } from "react";

export default function PendingApprovals() {
  const [approvals, setApprovals] = useState<any[]>([]);

  useEffect(() => {
    fetch("/api/v1/weights/pending?limit=10")
      .then((r) => r.json())
      .then((data) => setApprovals(data.pending || []));
  }, []);

  const handleApprove = (id: string) => {
    fetch(`/api/v1/weights/${id}/approve`, { method: "POST" })
      .then(() => setApprovals((prev) => prev.filter((a) => a.id !== id)));
  };

  return (
    <div className="p-4 border rounded">
      <h2 className="text-lg font-bold mb-2">Pending Weight Approvals</h2>
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
