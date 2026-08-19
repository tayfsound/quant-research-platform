import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Badge, EmptyState, ErrorNote, Spinner } from "../components/ui";

// Cognitive Core 2.0 / M10 (Faz 744-768) — kullanıcı onayıyla (2026-08-19)
// 4 Grup B modülü birlikte canlıya alındı. meta_optimizer/agent_tuner.py
// (CMA-ES) her onaylı tuning turunda sharpe_improvement kaydediyor — bu
// sayfa, turların ZAMAN İÇİNDE gerçekten bir iyileşme trendi mi
// gösterdiğini yoksa gürültü mü olduğunu (Spearman trend testi) gösterir.
// Sadece ölçüm/izleme, hiçbir tuning kararı otomatik onaylanmıyor.
type Trend = {
  spearman_correlation: number;
  p_value: number;
  trend: "improving" | "degrading" | "no_significant_trend";
  n_rounds: number;
  avg_sharpe_improvement: number;
};

type Result = { trend: Trend | null; n_approved_rounds: number };
type Report = { id: string; created_at: string; result: Result };

const TREND_LABEL: Record<string, string> = {
  improving: "İyileşiyor",
  degrading: "Kötüleşiyor",
  no_significant_trend: "Anlamlı trend yok",
};

const TREND_TONE: Record<string, "rise" | "fall" | "neutral"> = {
  improving: "rise",
  degrading: "fall",
  no_significant_trend: "neutral",
};

export default function MetaLearningEffectiveness() {
  const [live, setLive] = useState<Result | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    Promise.all([
      fetch("/api/v1/meta-learning-effectiveness/", { headers: authHeaders() }).then((r) => r.json()),
      fetch("/api/v1/meta-learning-effectiveness/reports?limit=20", { headers: authHeaders() }).then((r) => r.json()),
    ])
      .then(([liveData, history]) => {
        setLive(liveData.result || null);
        setReports(history.reports || []);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  return (
    <div>
      <PageHeader
        title="Meta-Learning Effectiveness"
        description="Spearman rank korelasyonu — ajan ayarlama (CMA-ES) turlarının zamanla gerçekten iyileşip iyileşmediğini test eder. Sadece tespit/rapor, hiçbir tuning kararı otomatik onaylanmıyor."
      />

      {error && <ErrorNote>{error}</ErrorNote>}

      <Card className="mb-6">
        <h3 className="text-sm font-semibold text-ink mb-1">Canlı ölçüm</h3>
        <p className="text-xs text-ink-soft mb-3">
          En az 8 onaylı tuning turu gerektirir — altında dürüstçe boş döner.
        </p>

        {loading ? (
          <Spinner />
        ) : !live || !live.trend ? (
          <EmptyState label={`Henüz yeterli onaylı tuning turu yok (${live?.n_approved_rounds ?? 0} tur var).`} />
        ) : (
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <Badge tone={TREND_TONE[live.trend.trend]}>{TREND_LABEL[live.trend.trend]}</Badge>
              <span className="text-xs text-ink-faint">
                Spearman ρ={live.trend.spearman_correlation.toFixed(4)}, p={live.trend.p_value.toFixed(6)}
              </span>
            </div>
            <p className="text-xs text-ink-soft">
              {live.trend.n_rounds} onaylı tur · ortalama sharpe_improvement:{" "}
              <span className="font-mono">{live.trend.avg_sharpe_improvement.toFixed(6)}</span>
            </p>
          </div>
        )}
      </Card>

      <Card>
        <h3 className="text-sm font-semibold text-ink mb-1">Haftalık rapor geçmişi</h3>
        {reports.length === 0 ? (
          <EmptyState label="Henüz hiçbir haftalık rapor oluşmadı — ilk rapor bir sonraki periyodik çalışmada kaydedilecek." />
        ) : (
          <div className="flex flex-col gap-2">
            {reports.map((r) => (
              <div key={r.id} className="text-xs text-ink-soft flex items-center justify-between border-b border-line-soft/50 pb-2">
                <span>{new Date(r.created_at).toLocaleString()}</span>
                <span className="font-mono">
                  {r.result.trend ? TREND_LABEL[r.result.trend.trend] : "yetersiz veri"} · {r.result.n_approved_rounds} tur
                </span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
