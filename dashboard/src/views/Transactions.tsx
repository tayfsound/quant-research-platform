import { useEffect, useState } from "react";
import { authHeaders } from "../api/auth";
import { PageHeader, Badge, EmptyState, StatCard } from "../components/ui";
import { useCurrency } from "../lib/currency";

type Position = {
  id: string;
  symbol: string;
  direction: string;
  entry_price: number | null;
  exit_price: number | null;
  quantity: number | null;
  status: string;
  pnl: number | null;
  stop_loss_price: number | null;
  take_profit_price: number | null;
  leverage: number | null;
  liquidation_price: number | null;
  exit_reason: string | null;
  opened_at: string | null;
  closed_at: string | null;
};

const EXIT_REASON_LABELS: Record<string, string> = {
  take_profit: "Hedefe ulaştı",
  stop_loss: "Stop oldu",
  time_expired: "Vadesi doldu",
  liquidation: "Likidasyon",
};

function fmt(n: number | null | undefined, digits = 2) {
  return n === null || n === undefined ? "—" : n.toFixed(digits);
}

export default function Transactions() {
  const [open, setOpen] = useState<Position[]>([]);
  const [trades, setTrades] = useState<Position[]>([]);
  const [summary, setSummary] = useState<{ count: number; win_rate: number; total_pnl: number } | null>(null);
  const { format, currency } = useCurrency();

  const load = () => {
    fetch("/api/v1/positions", { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => setOpen(data.positions || []));
    fetch("/api/v1/trades", { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => {
        setTrades(data.trades || []);
        setSummary(data.summary || null);
      });
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 15000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div>
      <PageHeader
        title="Transactions"
        description="AI'ın gerçekten açtığı ve kapattığı paper-trading işlemleri."
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <StatCard label="Açık pozisyon" value={open.length} />
        <StatCard label="Kapanmış işlem" value={summary?.count ?? 0} sub={summary ? `%${(summary.win_rate * 100).toFixed(0)} kazanma oranı` : undefined} />
        <StatCard
          label={`Toplam PnL (kapanmış, ${currency})`}
          value={summary ? format(summary.total_pnl) : "—"}
          tone={summary && summary.total_pnl > 0 ? "rise" : summary && summary.total_pnl < 0 ? "fall" : "neutral"}
        />
      </div>

      <h2 className="text-sm font-semibold text-ink-soft uppercase tracking-wide mb-3">Açık Pozisyonlar</h2>
      {open.length === 0 ? (
        <EmptyState label="Şu an açık pozisyon yok." />
      ) : (
        <div className="overflow-x-auto mb-8">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-ink-faint text-xs uppercase tracking-wide">
                <th className="py-2 pr-4">Sembol</th>
                <th className="py-2 pr-4">Yön</th>
                <th className="py-2 pr-4">Giriş Fiyatı</th>
                <th className="py-2 pr-4">Miktar</th>
                <th className="py-2 pr-4">Pozisyon Büyüklüğü</th>
                <th className="py-2 pr-4">Kaldıraç</th>
                <th className="py-2 pr-4">Stop / Hedef</th>
                <th className="py-2 pr-4">Açıldı</th>
              </tr>
            </thead>
            <tbody>
              {open.map((p) => (
                <tr key={p.id} className="border-t border-line-soft">
                  <td className="py-2 pr-4 font-mono text-ink">{p.symbol}</td>
                  <td className="py-2 pr-4">
                    <Badge tone={p.direction === "LONG" ? "rise" : "fall"}>{p.direction}</Badge>
                  </td>
                  <td className="py-2 pr-4 font-mono text-ink-soft">{format(p.entry_price)}</td>
                  <td className="py-2 pr-4 font-mono text-ink-soft">{fmt(p.quantity, 4)}</td>
                  <td className="py-2 pr-4 font-mono text-ink-soft">
                    {p.entry_price != null && p.quantity != null ? format(p.entry_price * p.quantity) : "—"}
                  </td>
                  <td className="py-2 pr-4">
                    {p.leverage && p.leverage > 1 ? (
                      <Badge tone="accent">{p.leverage}x</Badge>
                    ) : (
                      <span className="text-ink-faint text-xs">spot</span>
                    )}
                  </td>
                  <td className="py-2 pr-4 font-mono text-xs">
                    <span className="text-fall">{format(p.stop_loss_price)}</span>
                    {" / "}
                    <span className="text-rise">{format(p.take_profit_price)}</span>
                    {p.liquidation_price != null && (
                      <div className="text-fall/70 mt-0.5">likidasyon: {format(p.liquidation_price)}</div>
                    )}
                  </td>
                  <td className="py-2 pr-4 text-ink-faint">{p.opened_at ? new Date(p.opened_at).toLocaleString() : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2 className="text-sm font-semibold text-ink-soft uppercase tracking-wide mb-1">Kapanmış İşlemler</h2>
      {summary && summary.count > trades.length && (
        <p className="text-xs text-ink-faint mb-3">
          En son {trades.length} işlem gösteriliyor (toplam {summary.count} — üstteki özet kutuları
          her zaman gerçek toplamı yansıtır).
        </p>
      )}
      {trades.length === 0 ? (
        <EmptyState label="Henüz kapanmış işlem yok." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-ink-faint text-xs uppercase tracking-wide">
                <th className="py-2 pr-4">Sembol</th>
                <th className="py-2 pr-4">Yön</th>
                <th className="py-2 pr-4">Giriş</th>
                <th className="py-2 pr-4">Çıkış</th>
                <th className="py-2 pr-4">Pozisyon Büyüklüğü</th>
                <th className="py-2 pr-4">PnL</th>
                <th className="py-2 pr-4">Nasıl Kapandı</th>
                <th className="py-2 pr-4">Kapandı</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t) => (
                <tr key={t.id} className="border-t border-line-soft">
                  <td className="py-2 pr-4 font-mono text-ink">{t.symbol}</td>
                  <td className="py-2 pr-4">
                    <Badge tone={t.direction === "LONG" ? "rise" : "fall"}>{t.direction}</Badge>
                    {t.leverage && t.leverage > 1 && (
                      <span className="ml-1 text-xs text-accent font-medium">{t.leverage}x</span>
                    )}
                  </td>
                  <td className="py-2 pr-4 font-mono text-ink-soft">{format(t.entry_price)}</td>
                  <td className="py-2 pr-4 font-mono text-ink-soft">{format(t.exit_price)}</td>
                  <td className="py-2 pr-4 font-mono text-ink-soft">
                    {t.entry_price != null && t.quantity != null ? format(t.entry_price * t.quantity) : "—"}
                  </td>
                  <td className={`py-2 pr-4 font-mono ${t.pnl && t.pnl > 0 ? "text-rise" : t.pnl && t.pnl < 0 ? "text-fall" : "text-ink-soft"}`}>
                    {format(t.pnl)}
                  </td>
                  <td className="py-2 pr-4">
                    {t.exit_reason && (
                      <Badge tone={t.exit_reason === "take_profit" ? "rise" : (t.exit_reason === "stop_loss" || t.exit_reason === "liquidation") ? "fall" : "neutral"}>
                        {EXIT_REASON_LABELS[t.exit_reason] || t.exit_reason}
                      </Badge>
                    )}
                  </td>
                  <td className="py-2 pr-4 text-ink-faint">{t.closed_at ? new Date(t.closed_at).toLocaleString() : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
