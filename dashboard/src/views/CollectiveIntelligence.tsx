import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Badge, EmptyState, ErrorNote, Spinner } from "../components/ui";

// Cognitive Core 10.0 — kullanıcı isteği: council'i hiç etkilemeyen,
// ölçüm-only roadmap modüllerini birer birer canlıya alalım — Collective
// Intelligence, Causal Inference'tan sonraki Grup B adayı. Condorcet'in
// Jüri Teoremi (1785): her ajan bağımsız ve rastgeleden daha iyiyse
// (accuracy>0.5), çoğunluk oyunun beklenen doğruluğu HERHANGİ bir tekil
// ajandan yüksek olmalı. Bu sayfa 10-ajanlı council'in bu teoremi
// GERÇEKTEN karşılayıp karşılamadığını gösterir — sadece ölçüm/izleme,
// hiçbir ajan ağırlığı otomatik değişmiyor.
type CollectiveResult = {
  per_agent_accuracy: Record<string, number>;
  per_agent_sample_size: Record<string, number>;
  agents_included: string[];
  agents_excluded_insufficient_data: string[];
  condorcet: {
    expected_majority_accuracy: number;
    best_individual_accuracy: number;
    collective_beats_best_individual: boolean;
    n_agents: number;
  } | null;
};

type CollectiveReport = {
  id: string;
  created_at: string;
  result: CollectiveResult;
};

export default function CollectiveIntelligence() {
  const [live, setLive] = useState<CollectiveResult | null>(null);
  const [reports, setReports] = useState<CollectiveReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    Promise.all([
      fetch("/api/v1/collective-intelligence/", { headers: authHeaders() }).then((r) => r.json()),
      fetch("/api/v1/collective-intelligence/reports?limit=20", { headers: authHeaders() }).then((r) => r.json()),
    ])
      .then(([liveData, history]) => {
        setLive(liveData.result || null);
        setReports(history.reports || []);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const sortedAgents = live
    ? Object.entries(live.per_agent_accuracy).sort((a, b) => b[1] - a[1])
    : [];

  return (
    <div>
      <PageHeader
        title="Collective Intelligence"
        description="Condorcet'in Jüri Teoremi (1785) — 10-ajanlı council'in çoğunluk oyu, GERÇEKTEN en iyi tekil ajandan daha isabetli mi? Sadece ölçüm/izleme, hiçbir ajan ağırlığı otomatik değişmiyor."
      />

      {error && <ErrorNote>{error}</ErrorNote>}

      <Card className="mb-6">
        <h3 className="text-sm font-semibold text-ink mb-1">Canlı ölçüm</h3>
        <p className="text-xs text-ink-soft mb-3">
          Her ajanın son 20 gerçek yönlü kararının isabet oranı (SourceReliabilityAgent'ın kullandığı AYNI
          pencere) — yeterli örneklemi (≥10) olmayan ajanlar (WAIT-only time/epistemology dahil) dışarıda
          bırakılır.
        </p>

        {loading ? (
          <Spinner />
        ) : !live ? (
          <EmptyState label="Henüz veri yok." />
        ) : (
          <>
            {live.condorcet && (
              <div className="mb-4 p-3 rounded-lg border border-line-soft bg-canvas-soft">
                <div className="flex items-center gap-2 mb-1">
                  <Badge tone={live.condorcet.collective_beats_best_individual ? "rise" : "fall"}>
                    {live.condorcet.collective_beats_best_individual
                      ? "Council toplamı en iyi tekil ajandan daha isabetli"
                      : "Council toplamı en iyi tekil ajandan DAHA KÖTÜ"}
                  </Badge>
                </div>
                <p className="text-xs text-ink-soft">
                  Beklenen çoğunluk-oyu doğruluğu: <span className="font-mono">{(live.condorcet.expected_majority_accuracy * 100).toFixed(1)}%</span>
                  {" · "}En iyi tekil ajan: <span className="font-mono">{(live.condorcet.best_individual_accuracy * 100).toFixed(1)}%</span>
                  {" · "}{live.condorcet.n_agents} ajan dahil edildi
                </p>
                {!live.condorcet.collective_beats_best_individual && (
                  <p className="text-xs text-ink-faint mt-1">
                    Teorem, HERHANGİ bir ajanın rastgeleden daha iyi (accuracy&gt;%50) olmasını varsayıyor —
                    aşağıdaki tabloda %50'nin altında kalan ajanlar bu garantiyi bozuyor.
                  </p>
                )}
              </div>
            )}

            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-ink-faint border-b border-line-soft">
                    <th className="py-2 pr-4">Ajan</th>
                    <th className="py-2 pr-4">Son 20 karar isabeti</th>
                    <th className="py-2 pr-4">Örneklem</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedAgents.map(([domain, acc]) => (
                    <tr key={domain} className="border-b border-line-soft/50">
                      <td className="py-2 pr-4 text-ink font-medium">{domain}</td>
                      <td className="py-2 pr-4">
                        <Badge tone={acc >= 0.5 ? "rise" : "fall"}>{(acc * 100).toFixed(0)}%</Badge>
                      </td>
                      <td className="py-2 pr-4 text-ink-soft">{live.per_agent_sample_size[domain]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {live.agents_excluded_insufficient_data.length > 0 && (
              <p className="text-xs text-ink-faint mt-2">
                Yetersiz örneklem nedeniyle hariç: {live.agents_excluded_insufficient_data.join(", ")}
              </p>
            )}
          </>
        )}
      </Card>

      <Card>
        <h3 className="text-sm font-semibold text-ink mb-1">Haftalık rapor geçmişi</h3>
        <p className="text-xs text-ink-soft mb-3">
          services/tasks.py::refresh_collective_intelligence_report_task her hafta bir anlık görüntü
          kaydediyor — "council zaman içinde tek ajandan daha iyi mi kötü mü" sorusunu cevaplamak için.
        </p>
        {reports.length === 0 ? (
          <EmptyState label="Henüz hiçbir haftalık rapor oluşmadı — ilk rapor bir sonraki periyodik çalışmada kaydedilecek." />
        ) : (
          <div className="flex flex-col gap-2">
            {reports.map((r) => (
              <div key={r.id} className="text-xs text-ink-soft flex items-center justify-between border-b border-line-soft/50 pb-2">
                <span>{new Date(r.created_at).toLocaleString()}</span>
                <Badge tone={r.result.condorcet?.collective_beats_best_individual ? "rise" : "fall"}>
                  {r.result.condorcet?.collective_beats_best_individual ? "council kazandı" : "council kaybetti"}
                </Badge>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
