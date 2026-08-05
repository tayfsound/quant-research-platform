import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";

export default function ExperimentList() {
  const [experiments, setExperiments] = useState<any[]>([]);

  useEffect(() => {
    fetch("/api/v1/experiments/", { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => setExperiments(data.experiments || []));
  }, []);

  return (
    <div className="p-4 border rounded">
      <h2 className="text-lg font-bold mb-2">Experiments</h2>
      {experiments.length === 0 ? (
        <div>No experiments found</div>
      ) : (
        <div className="space-y-2">
          {experiments.map((e: any) => (
            <div key={e.id} className="text-sm p-2 bg-gray-50 rounded">
              <div>SHA: {e.git_sha?.slice(0, 8)}</div>
              <div>Decisions: {e.decision_count}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
