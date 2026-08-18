import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Badge, EmptyState, ErrorNote, Spinner } from "../components/ui";

// Cognitive Core 2.0 (Faz 469-493) — kullanıcı isteği: council'i hiç
// etkilemeyen, ölçüm-only roadmap modüllerini birer birer canlıya alalım
// — Collective Intelligence'tan sonraki Grup B adayı. Mevcut MAE/MFE nokta
// tahminleri (ör. p90 MAE = 0.023) küçük bir örneklemden mi büyük bir
// örneklemden mi geldiği hiç belli değildi — bu sayfa bootstrap resampling
// ile GERÇEK bir güven aralığı gösteriyor. Sadece ölçüm/izleme, hiçbir
// SL/TP kararı otomatik değişmiyor.
type ConfidenceInterval = {
  point_estimate: number;
  ci_lower: number;
  ci_upper: number;
  ci_level: number;
  sample_size: number;
};

type MaeMfeResult = {
  quantile: number;
  point_estimates: Record<string, { sample_size: number; mae_quantiles: Record<string, number>; mfe_median: number; win_rate: number }>;
  confidence_intervals: Record<string, ConfidenceInterval>;
  total_trades: number;
};

type MaeMfeReport = {
  id: string;
  created_at: string;
  result: MaeMfeResult;
};

export default function MaeMfeConfidence() {
  const [live, setLive] = useState<MaeMfeResult | null>(null);
  const [reports, setReports] = useState<MaeMfeReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    Promise.all([
      fetch("/api/v1/mae-mfe-confidence/", { headers: authHeaders() }).then((r) => r.json()),
      fetch("/api/v1/mae-mfe-confidence/reports?limit=20", { headers: authHeaders() }).then((r) => r.json()),
    ])
      .then(([liveData, history]) => {
        setLive(liveData.result || null);
        setReports(history.reports || []);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const groups = live ? Object.entries(live.confidence_intervals) : [];

  return (
    <div>
      <PageHeader
        title="MAE/MFE Güven Aralığı"
        description="Bootstrap resampling (Efron, 1979) — koşul kovası başına p90 MAE nokta tahmininin GERÇEK belirsizliği. Sadece ölçüm/izleme, hiçbir SL/TP kararı otomatik değişmiyor."
      />

      {error && <ErrorNote>{error}</ErrorNote>}

      <Card className="mb-6">
        <h3 className="text-sm font-semibold text-ink mb-1">Canlı ölçüm</h3>
        <p className="text-xs text-ink-soft mb-3">
          Kova başına (direction|regime|volatility_regime) p{live ? Math.round(live.quantile * 100) : 90} MAE nokta
          tahmini + %95 bootstrap güven aralığı — en az 10 örneklem gerektirir, altındaki kovalar hiç dönmez.
        </p>

        {loading ? (
          <Spinner />
        ) : !live || groups.length === 0 ? (
          <EmptyState label="Henüz yeterli örneklemli kova yok." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-ink-faint border-b border-line-soft">
                  <th className="py-2 pr-4">Kova</th>
                  <th className="py-2 pr-4">Nokta tahmini</th>
                  <th className="py-2 pr-4">%95 Güven Aralığı</th>
                  <th className="py-2 pr-4">Örneklem</th>
                </tr>
              </thead>
              <tbody>
                {groups.map(([label, ci]) => (
                  <tr key={label} className="border-b border-line-soft/50">
                    <td className="py-2 pr-4 text-ink font-medium">{label}</td>
                    <td className="py-2 pr-4 font-mono">{(ci.point_estimate * 100).toFixed(2)}%</td>
                    <td className="py-2 pr-4 font-mono">
                      [{(ci.ci_lower * 100).toFixed(2)}%, {(ci.ci_upper * 100).toFixed(2)}%]
                    </td>
                    <td className="py-2 pr-4">
                      <Badge tone={ci.sample_size >= 30 ? "rise" : "neutral"}>{ci.sample_size}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {live && (
          <p className="text-xs text-ink-faint mt-3">Toplam işlem havuzu: {live.total_trades}</p>
        )}
      </Card>

      <Card>
        <h3 className="text-sm font-semibold text-ink mb-1">Haftalık rapor geçmişi</h3>
        <p className="text-xs text-ink-soft mb-3">
          services/tasks.py::refresh_mae_mfe_confidence_report_task her hafta bir anlık görüntü kaydediyor —
          güven aralığının örneklem büyüdükçe daralıp daralmadığını izlemek için.
        </p>
        {reports.length === 0 ? (
          <EmptyState label="Henüz hiçbir haftalık rapor oluşmadı — ilk rapor bir sonraki periyodik çalışmada kaydedilecek." />
        ) : (
          <div className="flex flex-col gap-2">
            {reports.map((r) => (
              <div key={r.id} className="text-xs text-ink-soft flex items-center justify-between border-b border-line-soft/50 pb-2">
                <span>{new Date(r.created_at).toLocaleString()}</span>
                <span className="font-mono">{r.result.total_trades} işlem · {Object.keys(r.result.confidence_intervals || {}).length} kova</span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
