import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Badge, EmptyState, ErrorNote, Spinner } from "../components/ui";

// Faz 299-300 — kullanıcı isteği (2026-08-19): TP/SL için çok-yöntemli
// confluence ("zone of agreement" — S/R + Volume Profile + Pivot +
// Donchian + Keltner + Bollinger + Fibonacci, Faz 312). RiskTargetStage
// artık hedefi (SADECE hedefi,
// stop'u değil) gerçek bir yapısal bölgeye yakınsa sıkılaştırıyor —
// bu sayfa SADECE izleme: mevcut ATR-tabanlı hedefin watchlist
// genelinde gerçek yapısal desteğe ne sıklıkla denk geldiğini gösterir.
type SymbolResult = {
  symbol: string;
  confluence_zone_count: number;
  long_stop_near_confluence: boolean;
  long_target_near_confluence: boolean;
  short_stop_near_confluence: boolean;
  short_target_near_confluence: boolean;
};
type Result = {
  symbols_analyzed: number;
  avg_confluence_zones_per_symbol: number;
  pct_long_stop_near_confluence: number;
  pct_long_target_near_confluence: number;
  pct_short_stop_near_confluence: number;
  pct_short_target_near_confluence: number;
  by_symbol: SymbolResult[];
};
type Report = { id: string; created_at: string; result: Result };

export default function TpSlConfluence() {
  const [live, setLive] = useState<Result | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    Promise.all([
      fetch("/api/v1/tp-sl-confluence/", { headers: authHeaders() }).then((r) => r.json()),
      fetch("/api/v1/tp-sl-confluence/reports?limit=20", { headers: authHeaders() }).then((r) => r.json()),
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
        title="TP/SL Confluence"
        description="Zone of agreement — S/R zone clustering + Volume Profile POC/VA + Pivot Points + Donchian + Keltner + Bollinger + Fibonacci'den kaç BAĞIMSIZ yöntemin aynı fiyat bölgesinde birleştiği. RiskTargetStage artık hedefi (sadece hedefi) gerçek bir bölgeye yakınsa sıkılaştırıyor — bu sayfa mevcut ATR-tabanlı hedefin gerçek yapısal desteğe ne sıklıkla denk geldiğini izler."
      />

      {error && <ErrorNote>{error}</ErrorNote>}

      <Card className="mb-6">
        <h3 className="text-sm font-semibold text-ink mb-1">Canlı ölçüm</h3>
        <p className="text-xs text-ink-soft mb-3">
          Watchlist'teki {live?.symbols_analyzed ?? 0} sembol, ortalama {live?.avg_confluence_zones_per_symbol ?? 0} güçlü (≥2 yöntem) bölge/sembol.
        </p>

        {loading ? (
          <Spinner />
        ) : !live || live.symbols_analyzed === 0 ? (
          <EmptyState label="Henüz analiz edilecek yeterli veri yok." />
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="border border-line-soft rounded-lg p-3">
              <p className="text-xs text-ink-faint mb-1">LONG stop → yapısal bölge</p>
              <p className="text-lg font-mono text-ink">{(live.pct_long_stop_near_confluence * 100).toFixed(1)}%</p>
            </div>
            <div className="border border-line-soft rounded-lg p-3">
              <p className="text-xs text-ink-faint mb-1">LONG hedef → yapısal bölge</p>
              <p className="text-lg font-mono text-ink">{(live.pct_long_target_near_confluence * 100).toFixed(1)}%</p>
            </div>
            <div className="border border-line-soft rounded-lg p-3">
              <p className="text-xs text-ink-faint mb-1">SHORT stop → yapısal bölge</p>
              <p className="text-lg font-mono text-ink">{(live.pct_short_stop_near_confluence * 100).toFixed(1)}%</p>
            </div>
            <div className="border border-line-soft rounded-lg p-3">
              <p className="text-xs text-ink-faint mb-1">SHORT hedef → yapısal bölge</p>
              <p className="text-lg font-mono text-ink">{(live.pct_short_target_near_confluence * 100).toFixed(1)}%</p>
            </div>
          </div>
        )}

        {live && live.by_symbol.length > 0 && (
          <div className="overflow-x-auto mt-4">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-ink-faint text-left border-b border-line-soft">
                  <th className="py-2 pr-4">Sembol</th>
                  <th className="py-2 pr-4">Güçlü bölge sayısı</th>
                  <th className="py-2 pr-4">LONG hedef</th>
                  <th className="py-2 pr-4">SHORT hedef</th>
                </tr>
              </thead>
              <tbody>
                {live.by_symbol.map((r) => (
                  <tr key={r.symbol} className="border-b border-line-soft/50">
                    <td className="py-2 pr-4 font-mono text-ink">{r.symbol}</td>
                    <td className="py-2 pr-4 font-mono text-ink-soft">{r.confluence_zone_count}</td>
                    <td className="py-2 pr-4">
                      <Badge tone={r.long_target_near_confluence ? "rise" : "neutral"}>
                        {r.long_target_near_confluence ? "yakın" : "—"}
                      </Badge>
                    </td>
                    <td className="py-2 pr-4">
                      <Badge tone={r.short_target_near_confluence ? "rise" : "neutral"}>
                        {r.short_target_near_confluence ? "yakın" : "—"}
                      </Badge>
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
        {reports.length === 0 ? (
          <EmptyState label="Henüz hiçbir haftalık rapor oluşmadı — ilk rapor bir sonraki periyodik çalışmada kaydedilecek." />
        ) : (
          <div className="flex flex-col gap-2">
            {reports.map((r) => (
              <div key={r.id} className="text-xs text-ink-soft flex items-center justify-between border-b border-line-soft/50 pb-2">
                <span>{new Date(r.created_at).toLocaleString()}</span>
                <span className="font-mono">{r.result.symbols_analyzed} sembol analiz edildi</span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
