import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Badge, EmptyState, ErrorNote, Spinner } from "../components/ui";

// Cognitive Core 3.0 — kullanıcı isteği: council'i hiç etkilemeyen,
// ölçüm-only roadmap modüllerini birer birer canlıya alalım — Self-Model,
// ECE'den sonraki Grup B adayı. analytics/self_model.py::compute_self_
// reliability_snapshot() zaten hesaplanmış BAĞIMSIZ sinyalleri (ECE,
// Deflated Sharpe Ratio, kill switch, feature/concept drift) TEK bir
// öz-değerlendirme anlık görüntüsünde birleştiriyor. Bu sayfa SADECE
// ölçüm/izleme — hiçbir karar/risk parametresini otomatik değiştirmiyor.
type SelfModelInputs = {
  ece: number | null;
  recent_dsr: number | null;
  kill_switch_active: boolean;
  known_feature_drift_count: number;
  concept_drift_detected: boolean;
};

type SelfModelResult = {
  overall_reliability: "high" | "degraded" | "untrustworthy" | string;
  reliability_flags: string[];
  inputs: SelfModelInputs;
};

type SelfModelReport = {
  id: string;
  created_at: string;
  result: SelfModelResult;
};

function reliabilityTone(overall: string): "rise" | "warn" | "fall" | "neutral" {
  if (overall === "high") return "rise";
  if (overall === "degraded") return "warn";
  if (overall === "untrustworthy") return "fall";
  return "neutral";
}

function reliabilityLabel(overall: string): string {
  if (overall === "high") return "yüksek";
  if (overall === "degraded") return "zayıflamış";
  if (overall === "untrustworthy") return "güvenilmez";
  return overall;
}

function fmt(value: number | null, digits = 4): string {
  return value === null ? "—" : value.toFixed(digits);
}

export default function SelfModel() {
  const [live, setLive] = useState<SelfModelResult | null>(null);
  const [reports, setReports] = useState<SelfModelReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Kullanıcı bulgusu (2026-08-28): "Kill Switch aktif olduğu halde self
  // control kapalı gibi görünüyor" — sayfa SADECE ilk açılışta çekiyordu
  // (bkz. eski useEffect(load, [])), bir süre açık kalınca kill_switch_
  // active gibi hızlı değişen bir alan donmuş/bayat kalabiliyordu.
  // Dashboard.tsx'teki AYNI "sessiz arka plan yenileme" deseni — refresh()
  // loading spinner'ı TEKRAR tetiklemiyor, sadece veriyi günceller.
  const refresh = () => {
    return Promise.all([
      fetch("/api/v1/self-model/", { headers: authHeaders() }).then((r) => r.json()),
      fetch("/api/v1/self-model/reports?limit=20", { headers: authHeaders() }).then((r) => r.json()),
    ])
      .then(([liveData, history]) => {
        setLive(liveData.result || null);
        setReports(history.reports || []);
        setError(null);
      })
      .catch((e) => setError(String(e)));
  };

  const load = () => {
    setLoading(true);
    refresh().finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    const interval = setInterval(refresh, 60000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div>
      <PageHeader
        title="Self-Model"
        description="Sistemin kendi güvenilirliği hakkında halihazırda AYRI AYRI hesaplanan sinyalleri (kalibrasyon, Deflated Sharpe Ratio, kill switch, feature/concept drift) tek bir öz-değerlendirmede birleştirir — sadece ölçüm/izleme, hiçbir karar/risk parametresini otomatik değiştirmez."
      />

      {error && <ErrorNote>{error}</ErrorNote>}

      <Card className="mb-6">
        <h3 className="text-sm font-semibold text-ink mb-1">Canlı öz-değerlendirme</h3>
        <p className="text-xs text-ink-soft mb-3">Her sorguda gerçek alt sistemlerden taze hesaplanır.</p>

        {loading ? (
          <Spinner />
        ) : !live ? (
          <EmptyState label="Henüz veri yok." />
        ) : (
          <div>
            <div className="flex items-center gap-3 mb-4">
              <Badge tone={reliabilityTone(live.overall_reliability)}>
                {reliabilityLabel(live.overall_reliability)}
              </Badge>
              {live.reliability_flags.length === 0 ? (
                <span className="text-xs text-ink-faint">hiçbir uyarı bayrağı yok</span>
              ) : (
                live.reliability_flags.map((flag) => (
                  <Badge key={flag} tone="warn">
                    {flag}
                  </Badge>
                ))
              )}
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-ink-faint border-b border-line-soft">
                    <th className="py-2 pr-4">Girdi</th>
                    <th className="py-2 pr-4">Değer</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-b border-line-soft/50">
                    <td className="py-2 pr-4 text-ink-soft">ECE (kalibrasyon hatası)</td>
                    <td className="py-2 pr-4 font-mono text-ink">{fmt(live.inputs.ece)}</td>
                  </tr>
                  <tr className="border-b border-line-soft/50">
                    <td className="py-2 pr-4 text-ink-soft">Deflated Sharpe Ratio</td>
                    <td className="py-2 pr-4 font-mono text-ink">{fmt(live.inputs.recent_dsr)}</td>
                  </tr>
                  <tr className="border-b border-line-soft/50">
                    <td className="py-2 pr-4 text-ink-soft">Kill switch aktif mi</td>
                    <td className="py-2 pr-4">
                      <Badge tone={live.inputs.kill_switch_active ? "fall" : "neutral"}>
                        {live.inputs.kill_switch_active ? "evet" : "hayır"}
                      </Badge>
                    </td>
                  </tr>
                  <tr className="border-b border-line-soft/50">
                    <td className="py-2 pr-4 text-ink-soft">Drift tespit edilen feature sayısı</td>
                    <td className="py-2 pr-4 font-mono text-ink">{live.inputs.known_feature_drift_count}</td>
                  </tr>
                  <tr className="border-b border-line-soft/50">
                    <td className="py-2 pr-4 text-ink-soft">Concept drift tespit edildi mi</td>
                    <td className="py-2 pr-4">
                      <Badge tone={live.inputs.concept_drift_detected ? "fall" : "neutral"}>
                        {live.inputs.concept_drift_detected ? "evet" : "hayır"}
                      </Badge>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        )}
      </Card>

      <Card>
        <h3 className="text-sm font-semibold text-ink mb-1">Haftalık rapor geçmişi</h3>
        <p className="text-xs text-ink-soft mb-3">
          services/tasks.py::refresh_self_model_report_task her hafta bir anlık görüntü kaydediyor — "sistem
          kendi güvenilirliğini zaman içinde nasıl değerlendirdi" sorusunu cevaplamak için.
        </p>
        {reports.length === 0 ? (
          <EmptyState label="Henüz hiçbir haftalık rapor oluşmadı — ilk rapor bir sonraki periyodik çalışmada kaydedilecek." />
        ) : (
          <div className="flex flex-col gap-2">
            {reports.map((r) => (
              <div
                key={r.id}
                className="text-xs text-ink-soft flex items-center justify-between border-b border-line-soft/50 pb-2"
              >
                <span>{new Date(r.created_at).toLocaleString()}</span>
                <Badge tone={reliabilityTone(r.result.overall_reliability)}>
                  {reliabilityLabel(r.result.overall_reliability)}
                </Badge>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
