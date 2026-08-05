import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, StatCard, Badge, EmptyState } from "../components/ui";

export default function RiskDashboard() {
  const [limits, setLimits] = useState<any[]>([]);
  const [metrics, setMetrics] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch("/api/v1/risk-limits/", { headers: authHeaders() }).then((r) => r.json()),
      fetch("/api/v1/weights/metrics", { headers: authHeaders() }).then((r) => r.json()),
    ])
      .then(([limitsData, metricsData]) => {
        setLimits(limitsData.limits || []);
        setMetrics(metricsData);
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <PageHeader
        title="Risk"
        description="Gerçek, DB-backed, ADMIN-onaylı risk limitleri (Faz 172/gap #15) ve weight approval durumu."
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard label="Pending Approvals" value={metrics?.pending_count ?? "—"} />
        <StatCard
          label="Approval Latency (avg)"
          value={metrics?.latency?.avg_seconds != null ? `${metrics.latency.avg_seconds.toFixed(0)}s` : "—"}
        />
        <StatCard
          label="Approval Latency (p95)"
          value={metrics?.latency?.p95_seconds != null ? `${metrics.latency.p95_seconds.toFixed(0)}s` : "—"}
        />
        <StatCard label="Active Limits" value={limits.length} />
      </div>

      <Card>
        <h3 className="text-sm font-semibold text-ink mb-3">Active risk limits</h3>
        {loading ? (
          <p className="text-sm text-ink-soft">Loading…</p>
        ) : limits.length === 0 ? (
          <EmptyState label="Hiç risk limiti set edilmemiş — ADMIN rolüyle POST /risk-limits/{limit_type} ile bir limit ekleyin. Limit yoksa RiskEngine her kararı MISSING_LIMIT ile reddeder (bilinçli, fail-closed davranış)." />
        ) : (
          <div className="divide-y divide-line-soft">
            {limits.map((l) => (
              <div key={l.limit_type} className="flex items-center justify-between py-3">
                <div>
                  <div className="text-sm font-medium text-ink capitalize">{l.limit_type.replaceAll("_", " ")}</div>
                  <div className="text-xs text-ink-faint mt-0.5">
                    set by {l.created_by} · {new Date(l.created_at).toLocaleString()}
                  </div>
                </div>
                <Badge tone="accent">{l.value}</Badge>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
