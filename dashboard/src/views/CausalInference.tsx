import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Badge, EmptyState, ErrorNote, Spinner } from "../components/ui";

// Cognitive Core 4.0 — kullanıcı isteği: council'i hiç etkilemeyen,
// ölçüm-only roadmap modüllerini birer birer canlıya alalım — Causal
// Inference, Self-Model'den sonraki Grup B adayı. analytics/causal_
// inference.py::compute_granger_causality() standart bir "öngörücü
// nedensellik" testi (Granger, 1969) — sistemdeki diğer TÜM ilişki
// sinyallerinin (korelasyon tabanlı) aksine. Bu sayfa SADECE ölçüm/
// izleme — hiçbir karar/risk parametresini otomatik değiştirmiyor.
type CausalRelationship = {
  cause: string;
  effect: string;
  best_lag: number;
  best_p_value: number;
  sample_size: number;
};

type CausalResult = {
  cause_symbols_tested: string[];
  effect_symbols_tested: string[];
  pairs_tested: number;
  significant_relationships: CausalRelationship[];
};

type CausalReport = {
  id: string;
  created_at: string;
  result: CausalResult;
};

export default function CausalInference() {
  const [live, setLive] = useState<CausalResult | null>(null);
  const [reports, setReports] = useState<CausalReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    Promise.all([
      fetch("/api/v1/causal-inference/", { headers: authHeaders() }).then((r) => r.json()),
      fetch("/api/v1/causal-inference/reports?limit=20", { headers: authHeaders() }).then((r) => r.json()),
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
        title="Causal Inference"
        description="Granger causality (1969) — BTC/ETH'nin geçmiş getirileri, diğer varlıkların gelecekteki getirilerini SADECE kendi geçmişinin açıklayabileceğinden istatistiksel olarak anlamlı ölçüde fazla açıklıyor mu? Korelasyon değil, öngörücü nedensellik — sadece ölçüm/izleme, hiçbir karar otomatik değişmiyor."
      />

      {error && <ErrorNote>{error}</ErrorNote>}

      <Card className="mb-6">
        <h3 className="text-sm font-semibold text-ink mb-1">Canlı ölçüm</h3>
        <p className="text-xs text-ink-soft mb-3">
          Her sorguda gerçek 1h piyasa verisinden taze hesaplanır. Sadece istatistiksel olarak anlamlı (p&lt;0.05)
          ilişkiler listelenir, p-değerine göre en güçlüden en zayıfa sıralı.
        </p>

        {loading ? (
          <Spinner />
        ) : !live ? (
          <EmptyState label="Henüz veri yok." />
        ) : live.significant_relationships.length === 0 ? (
          <EmptyState label={`${live.pairs_tested} çift test edildi, şu an anlamlı bir ilişki bulunamadı.`} />
        ) : (
          <div className="overflow-x-auto">
            <p className="text-xs text-ink-faint mb-2">
              {live.pairs_tested} çift test edildi, {live.significant_relationships.length} anlamlı ilişki bulundu.
            </p>
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-ink-faint border-b border-line-soft">
                  <th className="py-2 pr-4">Sebep</th>
                  <th className="py-2 pr-4">Etki</th>
                  <th className="py-2 pr-4">En iyi gecikme (saat)</th>
                  <th className="py-2 pr-4">p-değeri</th>
                  <th className="py-2 pr-4">Örneklem</th>
                </tr>
              </thead>
              <tbody>
                {live.significant_relationships.map((r, i) => (
                  <tr key={`${r.cause}-${r.effect}-${i}`} className="border-b border-line-soft/50">
                    <td className="py-2 pr-4 font-mono text-ink">{r.cause}</td>
                    <td className="py-2 pr-4 font-mono text-ink">{r.effect}</td>
                    <td className="py-2 pr-4 text-ink-soft">{r.best_lag}</td>
                    <td className="py-2 pr-4">
                      <Badge tone={r.best_p_value < 0.01 ? "rise" : "accent"}>{r.best_p_value.toFixed(4)}</Badge>
                    </td>
                    <td className="py-2 pr-4 text-ink-soft">{r.sample_size}</td>
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
          services/tasks.py::refresh_causal_inference_report_task her hafta bir anlık görüntü kaydediyor —
          "BTC/ETH'nin öngörücülüğü zaman içinde nasıl değişti" sorusunu cevaplamak için.
        </p>
        {reports.length === 0 ? (
          <EmptyState label="Henüz hiçbir haftalık rapor oluşmadı — ilk rapor bir sonraki periyodik çalışmada kaydedilecek." />
        ) : (
          <div className="flex flex-col gap-2">
            {reports.map((r) => (
              <div key={r.id} className="text-xs text-ink-soft flex items-center justify-between border-b border-line-soft/50 pb-2">
                <span>{new Date(r.created_at).toLocaleString()}</span>
                <span>
                  {r.result.significant_relationships?.length ?? 0} anlamlı ilişki · {r.result.pairs_tested ?? 0} çift test edildi
                </span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
