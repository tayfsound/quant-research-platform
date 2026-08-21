import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Badge, EmptyState, ErrorNote, Spinner } from "../components/ui";

// Faz 338 — MetaStrategyAgent v1. "Bu stratejinin şu anki piyasa rejiminde
// gerçek edge'i var mı?" sorusuna GERÇEK kapanmış kararlardan cevap veren,
// ölçüm-only bir modül — pump_fade'in bugünkü felaketiyle doğrudan ilgili
// desenin (bullish rejimde SHORT-only strateji hâlâ tam boyutta) genel,
// tüm stratejiler için tekrarlanabilir hali. Hiçbir gate'e bağlı değil,
// sadece rapor.
type RegimeBucket = {
  sample_size: number;
  win_rate: number;
  win_rate_ci: { low: number; high: number; confidence_level: number };
  delta_vs_overall: number;
};

type StrategyEntry = {
  overall_win_rate: number | null;
  overall_sample_size: number;
  by_regime: Record<string, RegimeBucket>;
};

type Result = {
  by_strategy: Record<string, StrategyEntry>;
  n_decisions_analyzed: number;
};

function pct(v: number | null): string {
  return v === null ? "—" : `${(v * 100).toFixed(1)}%`;
}

function deltaTone(delta: number): "rise" | "warn" | "fall" | "neutral" {
  if (delta >= 0.1) return "rise";
  if (delta <= -0.1) return "fall";
  return "neutral";
}

export default function StrategyRegimeCompatibility() {
  const [result, setResult] = useState<Result | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetch("/api/v1/strategy-regime-compatibility/", { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => setResult(data.result || null))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <PageHeader
        title="Strateji × Rejim Uyumu"
        description="Her stratejinin (ai_council, pump_fade) piyasa rejimine göre gerçek kapanmış işlemlerdeki isabet oranını gösterir — bir strateji genel olarak iyi görünse bile belirli bir rejimde sistematik olarak kötü olabilir. Sadece ölçüm/rapor, hiçbir stratejiyi otomatik engellemez."
      />

      {error && <ErrorNote>{error}</ErrorNote>}

      {loading ? (
        <Spinner />
      ) : !result || Object.keys(result.by_strategy).length === 0 ? (
        <EmptyState label="Henüz yeterli kapanmış işlem yok." />
      ) : (
        <>
          <p className="text-xs text-ink-faint mb-4">
            {result.n_decisions_analyzed} kapanmış karar analiz edildi (son 5000, rejim etiketi olanlar).
          </p>
          {Object.entries(result.by_strategy).map(([strategy, entry]) => (
            <Card key={strategy} className="mb-6">
              <div className="flex items-center gap-3 mb-3">
                <h3 className="text-sm font-semibold text-ink">{strategy}</h3>
                <span className="text-xs text-ink-soft">
                  genel isabet {pct(entry.overall_win_rate)} (n={entry.overall_sample_size})
                </span>
              </div>

              {Object.keys(entry.by_regime).length === 0 ? (
                <EmptyState label="Hiçbir rejim kovası minimum örnek boyutuna ulaşmadı." />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-left text-ink-faint border-b border-line-soft">
                        <th className="py-2 pr-4">Rejim</th>
                        <th className="py-2 pr-4">n</th>
                        <th className="py-2 pr-4">İsabet</th>
                        <th className="py-2 pr-4">%95 CI</th>
                        <th className="py-2 pr-4">Genele göre fark</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(entry.by_regime).map(([regime, bucket]) => (
                        <tr key={regime} className="border-b border-line-soft/50">
                          <td className="py-2 pr-4 text-ink-soft">{regime}</td>
                          <td className="py-2 pr-4 font-mono text-ink">{bucket.sample_size}</td>
                          <td className="py-2 pr-4 font-mono text-ink">{pct(bucket.win_rate)}</td>
                          <td className="py-2 pr-4 font-mono text-ink-soft">
                            {pct(bucket.win_rate_ci.low)} – {pct(bucket.win_rate_ci.high)}
                          </td>
                          <td className="py-2 pr-4">
                            <Badge tone={deltaTone(bucket.delta_vs_overall)}>
                              {bucket.delta_vs_overall >= 0 ? "+" : ""}
                              {pct(bucket.delta_vs_overall)}
                            </Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          ))}
        </>
      )}
    </div>
  );
}
