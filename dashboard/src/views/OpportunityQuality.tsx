import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Badge, EmptyState, ErrorNote, Spinner } from "../components/ui";

// Cognitive Core 2.0 (Faz 569-593) — kullanıcı onayıyla (2026-08-19) 4
// Grup B modülü birlikte canlıya alındı. de Prado'nun meta-labeling
// ilkesi: council'daki ajanların yön oylarındaki ANLAŞMA derecesinin,
// gerçekleşen başarıyla ilişkili olup olmadığını ölçer. Sadece
// ölçüm/rapor, hiçbir pozisyon/risk kararı otomatik değişmiyor.
type BucketStat = { sample_size: number; win_rate: number };
type Result = { by_agreement_bucket: Record<string, BucketStat>; n_trades: number };
type Report = { id: string; created_at: string; result: Result };

const BUCKET_LABEL: Record<string, string> = { low: "Düşük anlaşma", medium: "Orta anlaşma", high: "Yüksek anlaşma" };
const BUCKET_ORDER = ["low", "medium", "high"];

export default function OpportunityQuality() {
  const [live, setLive] = useState<Result | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    Promise.all([
      fetch("/api/v1/opportunity-quality/", { headers: authHeaders() }).then((r) => r.json()),
      fetch("/api/v1/opportunity-quality/reports?limit=20", { headers: authHeaders() }).then((r) => r.json()),
    ])
      .then(([liveData, history]) => {
        setLive(liveData.result || null);
        setReports(history.reports || []);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const buckets = live
    ? BUCKET_ORDER.filter((b) => live.by_agreement_bucket[b]).map((b) => [b, live.by_agreement_bucket[b]] as const)
    : [];

  return (
    <div>
      <PageHeader
        title="Opportunity Quality"
        description="de Prado meta-labeling — council'in ajan-oyu ANLAŞMA derecesi (düşük/orta/yüksek) ile gerçekleşen kazanma oranı arasındaki ilişki. Sadece ölçüm/rapor, hiçbir pozisyon/risk kararı otomatik değişmiyor."
      />

      {error && <ErrorNote>{error}</ErrorNote>}

      <Card className="mb-6">
        <h3 className="text-sm font-semibold text-ink mb-1">Canlı ölçüm</h3>
        <p className="text-xs text-ink-soft mb-3">
          Her kova en az 20 örneklem gerektirir — {live?.n_trades ?? 0} toplam kapanmış işlem üzerinden.
        </p>

        {loading ? (
          <Spinner />
        ) : buckets.length === 0 ? (
          <EmptyState label="Henüz yeterli örneklemli kova yok." />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {buckets.map(([bucket, stat]) => (
              <div key={bucket} className="border border-line-soft rounded-lg p-3">
                <p className="text-xs text-ink-faint mb-1">{BUCKET_LABEL[bucket] ?? bucket}</p>
                <p className="text-lg font-mono text-ink">{(stat.win_rate * 100).toFixed(1)}%</p>
                <Badge tone={stat.win_rate >= 0.5 ? "rise" : "fall"}>{stat.sample_size} örneklem</Badge>
              </div>
            ))}
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
                <span className="font-mono">{r.result.n_trades} işlem · {Object.keys(r.result.by_agreement_bucket || {}).length} kova</span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
