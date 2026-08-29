import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Badge, EmptyState, ErrorNote, Spinner } from "../components/ui";

// Cognitive Core 2.0 (Faz 569-593) — kullanıcı onayıyla (2026-08-19) 4
// Grup B modülü birlikte canlıya alındı. de Prado'nun meta-labeling
// ilkesi: council'daki ajanların yön oylarındaki ANLAŞMA derecesinin,
// gerçekleşen başarıyla ilişkili olup olmadığını ölçer. Sadece
// ölçüm/rapor, hiçbir pozisyon/risk kararı otomatik değişmiyor.
type ConfidenceInterval = { low: number; high: number; confidence_level: number };
type BucketStat = { sample_size: number; win_rate: number; win_rate_ci: ConfidenceInterval | null };

// Faz B (2026-08-29) — kullanıcı isteği: ham "kaç ajan anlaştı" yerine
// anlaşma × GERÇEK güvenilirlik bileşik skoru. Aynı win_rate büyüklüğü
// tek başına yanıltıcı olabildiği için expectancy/median_pnl/profit_
// factor da eklendi — küçük çok sayıda kazanç + nadir dev kayıp AYNI
// win_rate'i verebilir, bu üçü bunu ayırt eder.
type QualityScoreStat = {
  sample_size: number;
  win_rate: number;
  win_rate_ci: ConfidenceInterval | null;
  expectancy: number;
  median_pnl: number;
  profit_factor: number | null;
};
type QualityScoreBucket = { overall: QualityScoreStat; by_regime: Record<string, QualityScoreStat> };

type Result = {
  by_agreement_bucket: Record<string, BucketStat>;
  by_quality_score_bucket: Record<string, QualityScoreBucket>;
  n_trades: number;
  n_trades_with_reliability: number;
};
type Report = { id: string; created_at: string; result: Result };

const BUCKET_LABEL: Record<string, string> = { low: "Düşük anlaşma", medium: "Orta anlaşma", high: "Yüksek anlaşma" };
const BUCKET_ORDER = ["low", "medium", "high"];
const QUALITY_BUCKET_LABEL: Record<string, string> = { low: "Düşük kalite", medium: "Orta kalite", high: "Yüksek kalite" };

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
  const qualityBuckets = live
    ? BUCKET_ORDER.filter((b) => live.by_quality_score_bucket?.[b]).map(
        (b) => [b, live.by_quality_score_bucket[b]] as const
      )
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
                {stat.win_rate_ci && (
                  <p className="text-xs text-ink-faint font-mono mb-1">
                    %95 CI: {(stat.win_rate_ci.low * 100).toFixed(0)}–{(stat.win_rate_ci.high * 100).toFixed(0)}%
                  </p>
                )}
                <Badge tone={stat.win_rate >= 0.5 ? "rise" : "fall"}>{stat.sample_size} örneklem</Badge>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card className="mb-6">
        <h3 className="text-sm font-semibold text-ink mb-1">Kalite skoru (anlaşma × güvenilirlik)</h3>
        <p className="text-xs text-ink-soft mb-3">
          Yukarıdaki "kaç ajan anlaştı" (agreement) tek başına yanıltıcı olabilir — anlaşan ajanların GERÇEKTEN
          güvenilir (agents/source_reliability_agent.py'nin 20/100/500 pencereli hesabı) olup olmadığını da
          hesaba katan bileşik bir skor: agreement × ortalama güvenilirlik. win_rate tek başına büyüklüğü
          göstermez — expectancy (işlem başına ortalama pnl), medyan pnl ve profit factor (kazanç/kayıp oranı)
          bunu tamamlıyor. {live?.n_trades_with_reliability ?? 0} işlem güvenilirlik verisiyle skorlandı.
        </p>
        {loading ? (
          <Spinner />
        ) : qualityBuckets.length === 0 ? (
          <EmptyState label="Henüz yeterli örneklemli kova yok." />
        ) : (
          <div className="flex flex-col gap-4">
            {qualityBuckets.map(([bucket, data]) => (
              <div key={bucket} className="border border-line-soft rounded-lg p-3">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs font-semibold text-ink">{QUALITY_BUCKET_LABEL[bucket] ?? bucket}</p>
                  <Badge tone={data.overall.expectancy >= 0 ? "rise" : "fall"}>{data.overall.sample_size} örneklem</Badge>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                  <div>
                    <p className="text-ink-faint">Kazanma oranı</p>
                    <p className="font-mono text-ink">{(data.overall.win_rate * 100).toFixed(1)}%</p>
                  </div>
                  <div>
                    <p className="text-ink-faint">Expectancy</p>
                    <p className={`font-mono ${data.overall.expectancy >= 0 ? "text-rise" : "text-fall"}`}>
                      {data.overall.expectancy >= 0 ? "+" : ""}
                      {data.overall.expectancy.toFixed(2)}
                    </p>
                  </div>
                  <div>
                    <p className="text-ink-faint">Medyan PnL</p>
                    <p className="font-mono text-ink-soft">{data.overall.median_pnl.toFixed(2)}</p>
                  </div>
                  <div>
                    <p className="text-ink-faint">Profit factor</p>
                    <p className="font-mono text-ink-soft">
                      {data.overall.profit_factor != null ? data.overall.profit_factor.toFixed(2) : "—"}
                    </p>
                  </div>
                </div>
                {Object.keys(data.by_regime).length > 0 && (
                  <div className="mt-3 overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-left text-ink-faint border-b border-line-soft">
                          <th className="py-1 pr-4">Rejim</th>
                          <th className="py-1 pr-4">Örneklem</th>
                          <th className="py-1 pr-4">Kazanma</th>
                          <th className="py-1 pr-4">Expectancy</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(data.by_regime).map(([regime, stat]) => (
                          <tr key={regime} className="border-b border-line-soft/50">
                            <td className="py-1 pr-4 font-mono text-ink-soft">{regime}</td>
                            <td className="py-1 pr-4 text-ink-soft">{stat.sample_size}</td>
                            <td className="py-1 pr-4 text-ink-soft">{(stat.win_rate * 100).toFixed(1)}%</td>
                            <td className={`py-1 pr-4 font-mono ${stat.expectancy >= 0 ? "text-rise" : "text-fall"}`}>
                              {stat.expectancy >= 0 ? "+" : ""}
                              {stat.expectancy.toFixed(2)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
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
