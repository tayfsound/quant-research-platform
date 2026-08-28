import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Badge, EmptyState, ErrorNote, Spinner } from "../components/ui";

// Faz 296 — kullanıcı isteği (2026-08-19): mevcut auto-bench SADECE
// davranışsal/geriye dönük doğruluk ölçüyordu, "bu ajanın oyu olmasaydı
// gerçekleşen kararlar farklı olur muydu" sorusuna hiç cevap vermiyordu.
// GERÇEK kapanmış kararların saklanmış agent_contributions'ından
// leave-one-out rekonstrüksiyon yapar. Sadece ölçüm/rapor, hiçbir
// ajanın canlı oy hakkı otomatik değişmiyor.
type DomainStat = {
  votes_cast: number;
  caused_trade_count: number;
  caused_trade_total_pnl: number;
  caused_trade_win_rate: number | null;
  caused_trade_win_rate_ci: { low: number; high: number; confidence_level: number } | null;
  flipped_direction_count: number;
  not_pivotal_count: number;
};
type Result = { by_domain: Record<string, DomainStat>; n_decisions_analyzed: number };
type Report = { id: string; created_at: string; result: Result };

const DOMAIN_LABEL: Record<string, string> = {
  technical: "Teknik", macro: "Makro", onchain: "On-chain", pattern: "Patern",
  quant: "Kantitatif", order_flow: "Emir Akışı", time: "Zaman",
  epistemology: "Epistemoloji", relative_strength: "Göreceli Güç",
  credit: "Kredi", volatility: "Volatilite", sentiment: "Duyarlılık",
};

// Faz 368-devam — GPT'nin "Agent Interaction & Incremental Information
// Layer" önerisi: yukarıdaki tablo her ajanı TEK BAŞINA ölçüyor, ama "A ve
// B birbirinin yerini mi tutuyor, yoksa ikisi de bağımsız mı gerçek bilgi
// taşıyor" sorusuna cevap vermiyor. Bu bölüm aynı kararı A+B ikisi birden
// çıkarılmış halde de yeniden sentezleyip nedensel bir ilişki etiketi
// üretiyor.
type PairStat = {
  n_both_voted: number;
  redundant_substitutes_count: number;
  substitution_rate: number;
  both_independently_pivotal_count: number;
  a_dominates_count: number;
  b_dominates_count: number;
  jointly_irrelevant_count: number;
  redundant_substitutes_total_pnl: number;
};
type PairwiseResult = { by_pair: Record<string, PairStat>; n_decisions_analyzed: number };

function relationshipSummary(s: PairStat): { label: string; tone: "fall" | "rise" | "neutral" } {
  if (s.substitution_rate >= 0.3) return { label: "büyük ölçüde birbirinin yerini tutuyor", tone: "fall" };
  if (s.both_independently_pivotal_count > s.redundant_substitutes_count) {
    return { label: "çoğunlukla bağımsız pivotal", tone: "rise" };
  }
  return { label: "karışık / az veri", tone: "neutral" };
}

export default function AgentAblation() {
  const [live, setLive] = useState<Result | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  const [pairwiseLive, setPairwiseLive] = useState<PairwiseResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    Promise.all([
      fetch("/api/v1/agent-ablation/", { headers: authHeaders() }).then((r) => r.json()),
      fetch("/api/v1/agent-ablation/reports?limit=20", { headers: authHeaders() }).then((r) => r.json()),
      fetch("/api/v1/agent-pairwise-ablation/", { headers: authHeaders() }).then((r) => r.json()),
    ])
      .then(([liveData, history, pairwiseData]) => {
        setLive(liveData.result || null);
        setReports(history.reports || []);
        setPairwiseLive(pairwiseData.result || null);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const rows = live
    ? Object.entries(live.by_domain).sort((a, b) => a[1].caused_trade_total_pnl - b[1].caused_trade_total_pnl)
    : [];

  const pairRows = pairwiseLive
    ? Object.entries(pairwiseLive.by_pair)
        .filter(([, s]) => s.n_both_voted >= 10)
        .sort((a, b) => b[1].substitution_rate - a[1].substitution_rate)
    : [];

  return (
    <div>
      <PageHeader
        title="Agent Ablation"
        description="Leave-one-out: her ajanın oyu SIFIRLANIP council yeniden sentezlenir — 'caused_trade' bu ajan olmasaydı yönlü bir belief bile oluşmaz, işlem hiç açılmazdı demek (toplam pnl gerçek nedensel katkı). Sadece ölçüm/rapor, hiçbir ajanın canlı oy hakkı otomatik değişmiyor."
      />

      {error && <ErrorNote>{error}</ErrorNote>}

      <Card className="mb-6">
        <h3 className="text-sm font-semibold text-ink mb-1">Canlı ölçüm</h3>
        <p className="text-xs text-ink-soft mb-3">
          {live?.n_decisions_analyzed ?? 0} kapanmış karar üzerinden, negatif toplam pnl'e göre sıralı (en zararlı üstte).
        </p>

        {loading ? (
          <Spinner />
        ) : rows.length === 0 ? (
          <EmptyState label="Henüz analiz edilecek yeterli karar yok." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-ink-faint text-left border-b border-line-soft">
                  <th className="py-2 pr-4">Ajan</th>
                  <th className="py-2 pr-4">Oy kullandığı karar</th>
                  <th className="py-2 pr-4">Neden oldu (caused_trade)</th>
                  <th className="py-2 pr-4">Toplam pnl (nedensel)</th>
                  <th className="py-2 pr-4">Kazanma oranı (%95 CI)</th>
                  <th className="py-2 pr-4">Yön değiştirdi</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(([domain, s]) => (
                  <tr key={domain} className="border-b border-line-soft/50">
                    <td className="py-2 pr-4 text-ink font-medium">{DOMAIN_LABEL[domain] ?? domain}</td>
                    <td className="py-2 pr-4 font-mono text-ink-soft">{s.votes_cast}</td>
                    <td className="py-2 pr-4 font-mono text-ink-soft">{s.caused_trade_count}</td>
                    <td className="py-2 pr-4">
                      {s.caused_trade_count > 0 ? (
                        <Badge tone={s.caused_trade_total_pnl >= 0 ? "rise" : "fall"}>
                          {s.caused_trade_total_pnl >= 0 ? "+" : ""}{s.caused_trade_total_pnl.toFixed(2)}
                        </Badge>
                      ) : (
                        <span className="text-ink-faint">—</span>
                      )}
                    </td>
                    <td className="py-2 pr-4 font-mono text-ink-soft">
                      {s.caused_trade_win_rate != null ? (
                        <>
                          {(s.caused_trade_win_rate * 100).toFixed(1)}%
                          {s.caused_trade_win_rate_ci && (
                            <span className="text-ink-faint">
                              {" "}({(s.caused_trade_win_rate_ci.low * 100).toFixed(0)}–{(s.caused_trade_win_rate_ci.high * 100).toFixed(0)}%)
                            </span>
                          )}
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="py-2 pr-4 font-mono text-ink-soft">{s.flipped_direction_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card className="mb-6">
        <h3 className="text-sm font-semibold text-ink mb-1">Agent Interaction — ikili nedensel ilişki</h3>
        <p className="text-xs text-ink-soft mb-3">
          Aynı kararda BİRLİKTE oy veren ajan çiftleri A+B ikisi birden çıkarılmış halde de yeniden
          sentezleniyor. Yüksek "birbirinin yerini tutma oranı" (substitution rate), A ile B'nin tek başına
          hiç pivotal olmasa da BİRLİKTE çıkınca sonucu değiştirdiği — yani birbirinin yedeği olduğu anlamına
          gelir. Sadece ≥10 ortak oy kullanılmış çiftler gösteriliyor (fail-closed).
        </p>
        {loading ? (
          <Spinner />
        ) : pairRows.length === 0 ? (
          <EmptyState label="Henüz yeterli ortak-oy örneklemi olan bir ajan çifti yok." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-ink-faint text-left border-b border-line-soft">
                  <th className="py-2 pr-4">Çift</th>
                  <th className="py-2 pr-4">Birlikte oy</th>
                  <th className="py-2 pr-4">Yerini tutma oranı</th>
                  <th className="py-2 pr-4">Bağımsız pivotal (ikisi de)</th>
                  <th className="py-2 pr-4">Değerlendirme</th>
                </tr>
              </thead>
              <tbody>
                {pairRows.map(([pair, s]) => {
                  const [a, b] = pair.split("|");
                  const summary = relationshipSummary(s);
                  return (
                    <tr key={pair} className="border-b border-line-soft/50">
                      <td className="py-2 pr-4 text-ink font-medium">
                        {DOMAIN_LABEL[a] ?? a} × {DOMAIN_LABEL[b] ?? b}
                      </td>
                      <td className="py-2 pr-4 font-mono text-ink-soft">{s.n_both_voted}</td>
                      <td className="py-2 pr-4 font-mono text-ink-soft">{(s.substitution_rate * 100).toFixed(1)}%</td>
                      <td className="py-2 pr-4 font-mono text-ink-soft">{s.both_independently_pivotal_count}</td>
                      <td className="py-2 pr-4">
                        <Badge tone={summary.tone}>{summary.label}</Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
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
                <span className="font-mono">{r.result.n_decisions_analyzed} karar · {Object.keys(r.result.by_domain || {}).length} ajan</span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
