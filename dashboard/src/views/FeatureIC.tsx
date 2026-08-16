import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Badge, EmptyState, ErrorNote, Spinner } from "../components/ui";

// Faz 268-sonrası — kullanıcı isteği: "Feature IC'yi karar hattına
// bağlama." analytics/feature_ic.py::compute_feature_ic() her isimli
// sinyalin (ör. RSI, trend, liquidity_condition) GERÇEK kapanmış
// işlemlerdeki ileri getiriyle korelasyonunu (Information Coefficient)
// ölçüyor. Bu sayfa SADECE ölçüm/izleme — hiçbir feature'ı otomatik
// pasifleştirmiyor, hiçbir ajan skorlamasını değiştirmiyor. Yeterli
// gerçek veri birikip anlamlı (istatistiksel olarak anlamlı, p<0.05)
// bir bulgu çıktığında, bir insan bu sayıları görüp kasıtlı bir
// kalibrasyon kararı verebilir.
type FeatureICEntry = {
  ic: number;
  p_value: number;
  sample_size: number;
  agent_domain: string;
};

type FeatureICReport = {
  id: string;
  created_at: string;
  features: Record<string, FeatureICEntry>;
  total_closed_trades: number;
};

function icTone(ic: number, pValue: number): "rise" | "fall" | "neutral" {
  if (pValue >= 0.05) return "neutral";
  return ic >= 0 ? "rise" : "fall";
}

export default function FeatureIC() {
  const [features, setFeatures] = useState<Record<string, FeatureICEntry>>({});
  const [reports, setReports] = useState<FeatureICReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    Promise.all([
      fetch("/api/v1/feature-ic/", { headers: authHeaders() }).then((r) => r.json()),
      fetch("/api/v1/feature-ic/reports?limit=20", { headers: authHeaders() }).then((r) => r.json()),
    ])
      .then(([live, history]) => {
        setFeatures(live.features || {});
        setReports(history.reports || []);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const sortedFeatures = Object.entries(features).sort((a, b) => a[1].ic - b[1].ic);

  return (
    <div>
      <PageHeader
        title="Feature IC"
        description="Her ajan sinyalinin GERÇEK kapanmış işlemlerdeki ileri getiriyle korelasyonu (Information Coefficient) — sadece ölçüm/izleme, hiçbir feature otomatik pasifleştirilmiyor."
      />

      {error && <ErrorNote>{error}</ErrorNote>}

      <Card className="mb-6">
        <h3 className="text-sm font-semibold text-ink mb-1">Canlı ölçüm</h3>
        <p className="text-xs text-ink-soft mb-3">
          Her sorguda gerçek kapanmış işlem geçmişinden taze hesaplanır. Sadece yeterli örneklemi (≥20) olan
          feature'lar listelenir — istatistiksel olarak anlamsız bir sayı hiç gösterilmez.
        </p>

        {loading ? (
          <Spinner />
        ) : sortedFeatures.length === 0 ? (
          <EmptyState label="Henüz hiçbir feature için yeterli gerçek örneklem birikmedi." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-ink-faint border-b border-line-soft">
                  <th className="py-2 pr-4">Feature</th>
                  <th className="py-2 pr-4">Ajan</th>
                  <th className="py-2 pr-4">IC</th>
                  <th className="py-2 pr-4">p-değeri</th>
                  <th className="py-2 pr-4">Örneklem</th>
                  <th className="py-2 pr-4">Anlamlılık</th>
                </tr>
              </thead>
              <tbody>
                {sortedFeatures.map(([name, entry]) => (
                  <tr key={name} className="border-b border-line-soft/50">
                    <td className="py-2 pr-4 font-mono text-ink">{name}</td>
                    <td className="py-2 pr-4 text-ink-soft">{entry.agent_domain}</td>
                    <td className="py-2 pr-4">
                      <Badge tone={icTone(entry.ic, entry.p_value)}>{entry.ic.toFixed(4)}</Badge>
                    </td>
                    <td className="py-2 pr-4 text-ink-soft">{entry.p_value.toFixed(4)}</td>
                    <td className="py-2 pr-4 text-ink-soft">{entry.sample_size}</td>
                    <td className="py-2 pr-4">
                      {entry.p_value < 0.05 ? (
                        <Badge tone="accent">anlamlı</Badge>
                      ) : (
                        <span className="text-ink-faint">yetersiz kanıt</span>
                      )}
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
          services/tasks.py::refresh_feature_ic_report_task her hafta bir anlık görüntü kaydediyor — "IC
          zamanla nasıl değişti" sorusunu cevaplamak için.
        </p>
        {reports.length === 0 ? (
          <EmptyState label="Henüz hiçbir haftalık rapor oluşmadı — ilk rapor bir sonraki periyodik çalışmada kaydedilecek." />
        ) : (
          <div className="flex flex-col gap-2">
            {reports.map((r) => (
              <div key={r.id} className="text-xs text-ink-soft flex items-center justify-between border-b border-line-soft/50 pb-2">
                <span>{new Date(r.created_at).toLocaleString()}</span>
                <span>
                  {Object.keys(r.features).length} feature ölçüldü · {r.total_closed_trades} kapanmış işlem
                </span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
