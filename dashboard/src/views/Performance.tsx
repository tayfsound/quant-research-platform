import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Badge, StatCard, ErrorNote, EmptyState, Spinner } from "../components/ui";
import { useCurrency } from "../lib/currency";

type Bucket = {
  period_start: string;
  trade_count: number;
  total_pnl: number;
  win_rate: number;
  roi_pct: number;
  roi_pct_on_deployed: number;
};

type AllTime = {
  trade_count: number;
  total_pnl: number;
  win_rate: number;
  roi_pct: number;
  roi_pct_on_deployed: number;
  deployed_notional: number;
  excluded_dirty_trades_count: number;
};

type PerformanceData = {
  starting_capital: number;
  all_time: AllTime;
  daily: Bucket[];
  weekly: Bucket[];
  monthly: Bucket[];
  yearly: Bucket[];
};

const TABS: { key: keyof Pick<PerformanceData, "daily" | "weekly" | "monthly" | "yearly">; label: string }[] = [
  { key: "daily", label: "Günlük" },
  { key: "weekly", label: "Haftalık" },
  { key: "monthly", label: "Aylık" },
  { key: "yearly", label: "Yıllık" },
];

export default function Performance() {
  const [data, setData] = useState<PerformanceData | null>(null);
  const [tab, setTab] = useState<"daily" | "weekly" | "monthly" | "yearly">("daily");
  const [error, setError] = useState<string | null>(null);
  const { format, currency } = useCurrency();

  const load = () => {
    fetch("/api/v1/performance", { headers: authHeaders() })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(setData)
      .catch((e) => setError(String(e.message || e)));
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div>
      <PageHeader
        title="Performance"
        description="Gerçek kapanmış işlemlerden PnL/ROI — günlük, haftalık, aylık, yıllık."
      />

      {error && <ErrorNote>{error}</ErrorNote>}

      {!data && !error && (
        <div className="flex justify-center py-12">
          <Spinner />
        </div>
      )}

      {data && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
            <StatCard label="Toplam işlem" value={data.all_time.trade_count} />
            <StatCard
              label="Kazanma oranı"
              value={`%${(data.all_time.win_rate * 100).toFixed(0)}`}
            />
            <StatCard
              label={`Toplam PnL (${currency})`}
              value={format(data.all_time.total_pnl)}
              tone={data.all_time.total_pnl > 0 ? "rise" : data.all_time.total_pnl < 0 ? "fall" : "neutral"}
            />
            <StatCard
              label="Strateji getirisi (kullanılan sermayeye göre)"
              value={`%${(data.all_time.roi_pct_on_deployed * 100).toFixed(3)}`}
              tone={data.all_time.roi_pct_on_deployed > 0 ? "rise" : data.all_time.roi_pct_on_deployed < 0 ? "fall" : "neutral"}
              sub={`kullanılan: ${format(data.all_time.deployed_notional)}`}
            />
          </div>

          <p className="text-xs text-ink-soft mb-4">
            Kasa büyüklüğüne göre ROI: %{(data.all_time.roi_pct * 100).toFixed(6)} (sermaye:{" "}
            {data.starting_capital.toLocaleString()} — test için çok büyük bir değere ayarlıysa bu oran
            her zaman ~0 görünür, stratejinin gerçek performansı yukarıdaki "kullanılan sermayeye göre"
            değeridir).
          </p>

          {data.all_time.excluded_dirty_trades_count > 0 && (
            <p className="text-xs text-ink-faint mb-4">
              Not: {data.all_time.excluded_dirty_trades_count} adet kirli işlem (aşırı test ayarlarından kalan
              gerçek olmayan büyüklükteki işlemler ve geçmişte bir veri sağlayıcı hatası yüzünden gerçek dışı
              fiyatla kapanmış işlemler) yukarıdaki istatistiklerden hariç tutuldu (silinmedi, sadece
              istatistiklere dahil edilmedi).
            </p>
          )}

          <div className="flex gap-1 mb-4">
            {TABS.map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium ${
                  tab === t.key ? "bg-accent text-white" : "bg-canvas-soft text-ink-soft hover:text-ink"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          <Card padded={false}>
            {data[tab].length === 0 ? (
              <div className="p-5">
                <EmptyState label="Bu dönem için henüz kapanmış işlem yok." />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-ink-faint uppercase tracking-wide border-b border-line-soft">
                      <th className="px-5 py-2 font-medium">Dönem</th>
                      <th className="px-5 py-2 font-medium">İşlem</th>
                      <th className="px-5 py-2 font-medium">Kazanma oranı</th>
                      <th className="px-5 py-2 font-medium">PnL</th>
                      <th className="px-5 py-2 font-medium">Strateji getirisi</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data[tab].map((b) => (
                      <tr key={b.period_start} className="border-b border-line-soft last:border-0">
                        <td className="px-5 py-2.5 text-ink-soft text-xs">
                          {new Date(b.period_start).toLocaleDateString()}
                        </td>
                        <td className="px-5 py-2.5 text-ink-soft">{b.trade_count}</td>
                        <td className="px-5 py-2.5">
                          <Badge tone={b.win_rate >= 0.5 ? "rise" : "fall"}>{(b.win_rate * 100).toFixed(0)}%</Badge>
                        </td>
                        <td className={`px-5 py-2.5 font-medium ${b.total_pnl >= 0 ? "text-rise" : "text-fall"}`}>
                          {format(b.total_pnl)}
                        </td>
                        <td className={`px-5 py-2.5 font-medium ${b.roi_pct_on_deployed >= 0 ? "text-rise" : "text-fall"}`}>
                          {(b.roi_pct_on_deployed * 100).toFixed(3)}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
