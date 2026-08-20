import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Badge, EmptyState, ErrorNote, Spinner } from "../components/ui";

// Faz 331 — kullanıcı isteği (harici bir AI incelemesinin önerdiği,
// defalarca gündeme gelip ertelenen bir madde): Opportunity Quality
// (analytics/opportunity_quality.py) council'de KAÇ ajanın anlaştığını
// win_rate ile ilişkilendiriyor — bu sayfa HANGİ ajan İKİLİLERİNİN
// birlikte anlaştığını ilişkilendiriyor. Sadece ölçüm/izleme — hiçbir
// ajan ağırlığını/karar mantığını otomatik değiştirmiyor.
type CombinationPair = {
  domain_a: string;
  domain_b: string;
  sample_size: number;
  win_rate: number;
  win_rate_ci: { low: number; high: number; confidence_level: number };
  win_rate_delta_vs_baseline: number;
  fdr_significant: boolean;
};

type CombinationResult = {
  pairs: CombinationPair[];
  baseline_win_rate: number | null;
  baseline_sample_size: number;
  n_trades: number;
};

type CombinationReport = {
  id: string;
  created_at: string;
  result: CombinationResult;
};

export default function AgentCombinationReliability() {
  const [live, setLive] = useState<CombinationResult | null>(null);
  const [reports, setReports] = useState<CombinationReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    Promise.all([
      fetch("/api/v1/agent-combination-reliability/", { headers: authHeaders() }).then((r) => r.json()),
      fetch("/api/v1/agent-combination-reliability/reports?limit=20", { headers: authHeaders() }).then((r) => r.json()),
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
        title="Ajan Kombinasyonu Güvenilirliği"
        description="Opportunity Quality KAÇ ajanın anlaştığını ölçüyor — bu sayfa HANGİ ajan ikililerinin birlikte anlaştığını ölçüyor. Her ikili bağımsız test edildiği için (36 çift), çoklu-test düzeltmesi (Benjamini-Hochberg FDR) uygulanıyor — sadece ölçüm/izleme, hiçbir ajan ağırlığı otomatik değişmiyor."
      />

      {error && <ErrorNote>{error}</ErrorNote>}

      <Card className="mb-6">
        <h3 className="text-sm font-semibold text-ink mb-1">Canlı ölçüm</h3>
        <p className="text-xs text-ink-soft mb-3">
          Her sorguda gerçek kapanmış işlemlerden taze hesaplanır. Bir ikili, en az 20 gerçek işlemde birlikte
          nihai yönle aynı yönde oy vermişse listelenir, kazanma oranına göre en yüksekten en düşüğe sıralı.
        </p>

        {loading ? (
          <Spinner />
        ) : !live || live.pairs.length === 0 ? (
          <EmptyState label={`Henüz yeterli veri yok (${live?.n_trades ?? 0} işlem, min. 20 örneklem/ikili gerekiyor).`} />
        ) : (
          <div className="overflow-x-auto">
            <p className="text-xs text-ink-faint mb-2">
              {live.n_trades} işlem incelendi, genel ortalama kazanma oranı{" "}
              <strong>%{((live.baseline_win_rate ?? 0) * 100).toFixed(1)}</strong> ({live.baseline_sample_size} işlem).{" "}
              {live.pairs.length} ikili yeterli örnekleme sahip, bunlardan{" "}
              <strong>{live.pairs.filter((p) => p.fdr_significant).length}</strong> tanesi çoklu-test düzeltmesinden
              (FDR) sonra da anlamlı.
            </p>
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-ink-faint border-b border-line-soft">
                  <th className="py-2 pr-4">Ajan A</th>
                  <th className="py-2 pr-4">Ajan B</th>
                  <th className="py-2 pr-4">Kazanma oranı</th>
                  <th className="py-2 pr-4">Baseline'a göre fark</th>
                  <th className="py-2 pr-4">Örneklem</th>
                  <th className="py-2 pr-4">FDR sonrası</th>
                </tr>
              </thead>
              <tbody>
                {live.pairs.map((p, i) => (
                  <tr key={`${p.domain_a}-${p.domain_b}-${i}`} className="border-b border-line-soft/50">
                    <td className="py-2 pr-4 font-mono text-ink">{p.domain_a}</td>
                    <td className="py-2 pr-4 font-mono text-ink">{p.domain_b}</td>
                    <td className="py-2 pr-4">
                      <Badge tone={p.win_rate >= 0.8 ? "rise" : "accent"}>%{(p.win_rate * 100).toFixed(1)}</Badge>
                    </td>
                    <td className={`py-2 pr-4 ${p.win_rate_delta_vs_baseline >= 0 ? "text-rise" : "text-fall"}`}>
                      {p.win_rate_delta_vs_baseline >= 0 ? "+" : ""}
                      {(p.win_rate_delta_vs_baseline * 100).toFixed(1)} puan
                    </td>
                    <td className="py-2 pr-4 text-ink-soft">{p.sample_size}</td>
                    <td className="py-2 pr-4">
                      {p.fdr_significant ? <Badge tone="rise">geçti ✓</Badge> : <Badge tone="neutral">elendi</Badge>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card>
        <h3 className="text-sm font-semibold text-ink mb-1">Haftalık rapor geçmişi</h3>
        <p className="text-xs text-ink-soft mb-3">
          services/tasks.py::refresh_agent_combination_reliability_report_task her hafta bir anlık görüntü
          kaydediyor — "hangi ajan ikilisinin güvenilirliği zaman içinde nasıl değişti" sorusunu cevaplamak için.
        </p>
        {reports.length === 0 ? (
          <EmptyState label="Henüz hiçbir haftalık rapor oluşmadı — ilk rapor bir sonraki periyodik çalışmada kaydedilecek." />
        ) : (
          <div className="flex flex-col gap-2">
            {reports.map((r) => (
              <div key={r.id} className="text-xs text-ink-soft flex items-center justify-between border-b border-line-soft/50 pb-2">
                <span>{new Date(r.created_at).toLocaleString()}</span>
                <span>
                  {r.result.pairs?.length ?? 0} ikili · {r.result.n_trades ?? 0} işlem incelendi
                </span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
