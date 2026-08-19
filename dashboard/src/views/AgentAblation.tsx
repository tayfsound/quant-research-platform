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
};

export default function AgentAblation() {
  const [live, setLive] = useState<Result | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    Promise.all([
      fetch("/api/v1/agent-ablation/", { headers: authHeaders() }).then((r) => r.json()),
      fetch("/api/v1/agent-ablation/reports?limit=20", { headers: authHeaders() }).then((r) => r.json()),
    ])
      .then(([liveData, history]) => {
        setLive(liveData.result || null);
        setReports(history.reports || []);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const rows = live
    ? Object.entries(live.by_domain).sort((a, b) => a[1].caused_trade_total_pnl - b[1].caused_trade_total_pnl)
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
