import { useEffect, useMemo, useState } from "react";
import { authHeaders } from "../api/auth";
import { PageHeader, Badge, EmptyState, StatCard, Button } from "../components/ui";
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
  realized_pnl: number | null;
  stop_loss_price: number | null;
  take_profit_price: number | null;
  leverage: number | null;
  liquidation_price: number | null;
  timeframe: string | null;
  exit_reason: string | null;
  opened_at: string | null;
  closed_at: string | null;
};

// Faz 268: kullanıcı isteği — "aşamalı kapama, pozisyonun yarısını/
// çeyreğini kademeli kapatabilen mekanizma." Backend fraction'ı (0, 1]
// aralığında kabul ediyor; 1.0 kalanın tamamını (gerçek bir tam kapanış)
// kapatıyor.
const PARTIAL_CLOSE_OPTIONS: { label: string; fraction: number }[] = [
  { label: "%25 Kapat", fraction: 0.25 },
  { label: "%50 Kapat", fraction: 0.5 },
  { label: "Tümünü Kapat", fraction: 1.0 },
];

const EXIT_REASON_LABELS: Record<string, string> = {
  take_profit: "Hedefe ulaştı",
  stop_loss: "Stop oldu",
  time_expired: "Vadesi doldu",
  liquidation: "Likidasyon",
};

// Faz 259: orta-vadeli katman kısa-vadeliden ayrı bir sinyal zaman dilimi
// kullanıyor (4h/1d) — dashboard'da hangi pozisyonun hangi katmandan
// geldiğini ayırt edebilmek için.
const MEDIUM_TERM_TIMEFRAMES = new Set(["4h", "1d"]);

function fmt(n: number | null | undefined, digits = 2) {
  return n === null || n === undefined ? "—" : n.toFixed(digits);
}

// Gerçek bulgu (Faz 260): risk/ATR formülü her değiştiğinde, dashboard'da
// görünen "son N işlem" bir süre eski formülle açılmış pozisyonlardan
// oluşmaya devam ediyor — kullanıcı her seferinde bunu YENİ formülün
// başarısızlığı sanıyordu. Bu filtre, "sadece gerçekten yakın zamanda
// kapananları göster" diyebilmek için — sunucu tarafında bir şey
// değişmiyor, zaten çekilmiş olan `trades` listesi client-side süzülüyor.
//
// Faz 268c — kullanıcı bulgusu: "Bugün 8 işlem kapanmış diye gördüm
// Transactions'ta, Performance'ın günlüğünde 2 yazıyor." Gerçek veriyle
// doğrulandı: İKİSİ DE doğruydu, sadece "bugün"ün TANIMI farklıydı.
// "Son 24 saat" burada her zaman KAYAN bir pencereydi (şu andan geriye
// 24 saat, gün sınırı gözetmeden) — Performance'ın "Günlük" sekmesi ise
// SQL date_trunc('day', closed_at) ile TAKVİM GÜNÜ (UTC 00:00'dan
// itibaren) kullanıyor. Gün henüz birkaç saatliyken bu iki sayı doğal
// olarak farklı çıkar. TODAY_UTC_SENTINEL, Performance'ınkiyle AYNI
// tanımı (UTC takvim günü) kullanan gerçek bir "Bugün" seçeneği ekliyor
// — artık ikisi karşılaştırılabilir, biri diğerinin "hatası" değil.
const TODAY_UTC_SENTINEL = -1;

const SINCE_OPTIONS: { label: string; minutes: number | null }[] = [
  { label: "Bugün (UTC takvim günü)", minutes: TODAY_UTC_SENTINEL },
  { label: "Son 24 saat (kayan pencere)", minutes: 1440 },
  { label: "Son 1 saat", minutes: 60 },
  { label: "Son 15 dk", minutes: 15 },
  { label: "Tümü", minutes: null },
];

function sinceCutoffMs(minutes: number): number {
  if (minutes === TODAY_UTC_SENTINEL) {
    const now = new Date();
    return Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  }
  return Date.now() - minutes * 60_000;
}

export default function Transactions({ onSelectSymbol }: { onSelectSymbol?: (symbol: string) => void } = {}) {
  const [open, setOpen] = useState<Position[]>([]);
  const [openSummary, setOpenSummary] = useState<{ open_count: number; committed_notional: number } | null>(null);
  const [trades, setTrades] = useState<Position[]>([]);
  const [summary, setSummary] = useState<{ count: number; win_rate: number; total_pnl: number } | null>(null);
  const [sinceMinutes, setSinceMinutes] = useState<number | null>(null);
  const [closingId, setClosingId] = useState<string | null>(null);
  const [closeError, setCloseError] = useState<string | null>(null);
  const { format, currency } = useCurrency();

  const filteredTrades = useMemo(() => {
    if (sinceMinutes === null) return trades;
    const cutoff = sinceCutoffMs(sinceMinutes);
    return trades.filter((t) => t.closed_at && new Date(t.closed_at).getTime() >= cutoff);
  }, [trades, sinceMinutes]);

  const filteredSummary = useMemo(() => {
    if (sinceMinutes === null) return null;
    const wins = filteredTrades.filter((t) => (t.pnl ?? 0) > 0).length;
    const totalPnl = filteredTrades.reduce((sum, t) => sum + (t.pnl ?? 0), 0);
    return {
      count: filteredTrades.length,
      win_rate: filteredTrades.length ? wins / filteredTrades.length : 0,
      total_pnl: totalPnl,
    };
  }, [filteredTrades, sinceMinutes]);

  const load = () => {
    fetch("/api/v1/positions", { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => {
        setOpen(data.positions || []);
        setOpenSummary(data.summary || null);
      });
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

  const partialClose = async (id: string, fraction: number) => {
    setCloseError(null);
    setClosingId(id);
    try {
      const res = await fetch(`/api/v1/positions/${id}/partial-close`, {
        method: "POST",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ fraction }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `İstek başarısız oldu (${res.status})`);
      }
      load();
    } catch (err) {
      setCloseError(err instanceof Error ? err.message : "Kapatma işlemi başarısız oldu.");
    } finally {
      setClosingId(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="Transactions"
        description="AI'ın gerçekten açtığı ve kapattığı paper-trading işlemleri."
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <StatCard label="Açık pozisyon" value={openSummary?.open_count ?? open.length} />
        <StatCard label="Kapanmış işlem" value={summary?.count ?? 0} sub={summary ? `%${(summary.win_rate * 100).toFixed(0)} kazanma oranı` : undefined} />
        <StatCard
          label={`Toplam PnL (kapanmış, ${currency})`}
          value={summary ? format(summary.total_pnl) : "—"}
          tone={summary && summary.total_pnl > 0 ? "rise" : summary && summary.total_pnl < 0 ? "fall" : "neutral"}
        />
      </div>

      <h2 className="text-sm font-semibold text-ink-soft uppercase tracking-wide mb-1">Açık Pozisyonlar</h2>
      {closeError && (
        <p className="text-xs text-fall mb-3">{closeError}</p>
      )}
      {openSummary && openSummary.open_count > open.length && (
        <p className="text-xs text-ink-faint mb-3">
          En son {open.length} pozisyon gösteriliyor (toplam {openSummary.open_count} — üstteki özet kutusu
          her zaman gerçek toplamı yansıtır).
        </p>
      )}
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
                <th className="py-2 pr-4">Aşamalı Kapama</th>
              </tr>
            </thead>
            <tbody>
              {open.map((p) => (
                <tr key={p.id} className="border-t border-line-soft">
                  <td className="py-2 pr-4 font-mono text-ink">
                    {onSelectSymbol ? (
                      <button
                        onClick={() => onSelectSymbol(p.symbol)}
                        className="hover:underline hover:text-accent transition-colors"
                        title={`${p.symbol} grafiğini aç`}
                      >
                        {p.symbol}
                      </button>
                    ) : (
                      p.symbol
                    )}
                    {p.timeframe && MEDIUM_TERM_TIMEFRAMES.has(p.timeframe) && (
                      <span className="ml-1"><Badge tone="accent">orta vadeli</Badge></span>
                    )}
                  </td>
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
                  <td className="py-2 pr-4">
                    <div className="flex flex-wrap gap-1.5">
                      {PARTIAL_CLOSE_OPTIONS.map((opt) => (
                        <Button
                          key={opt.label}
                          variant={opt.fraction === 1.0 ? "danger" : "secondary"}
                          disabled={closingId === p.id}
                          onClick={() => partialClose(p.id, opt.fraction)}
                          className="!px-2 !py-1 text-xs"
                        >
                          {opt.label}
                        </Button>
                      ))}
                    </div>
                    {p.realized_pnl != null && (
                      <div className="text-xs text-ink-faint mt-1">
                        Realize edilen: <span className={p.realized_pnl > 0 ? "text-rise" : p.realized_pnl < 0 ? "text-fall" : ""}>{format(p.realized_pnl)}</span>
                      </div>
                    )}
                  </td>
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

      <div className="flex flex-wrap items-center gap-2 mb-3">
        {SINCE_OPTIONS.map((opt) => (
          <button
            key={opt.label}
            onClick={() => setSinceMinutes(opt.minutes)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
              sinceMinutes === opt.minutes
                ? "bg-accent text-white border-accent"
                : "bg-canvas-soft text-ink-soft border-line hover:bg-surface-soft"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {filteredSummary && (
        <p className="text-xs text-ink-faint mb-3">
          {filteredSummary.count === 0
            ? "Bu aralıkta henüz kapanmış işlem yok — yukarıdaki genel özet daha eski işlemleri yansıtıyor."
            : `Bu aralıkta ${filteredSummary.count} işlem kapandı — %${(filteredSummary.win_rate * 100).toFixed(0)} kazanma oranı, ${format(filteredSummary.total_pnl)} toplam PnL.`}
        </p>
      )}

      {filteredTrades.length === 0 ? (
        <EmptyState label={sinceMinutes === null ? "Henüz kapanmış işlem yok." : "Bu aralıkta kapanmış işlem yok."} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-ink-faint text-xs uppercase tracking-wide">
                <th className="py-2 pr-4">Sembol</th>
                <th className="py-2 pr-4">Yön</th>
                <th className="py-2 pr-4">Giriş</th>
                <th className="py-2 pr-4">Çıkış</th>
                <th className="py-2 pr-4">Stop / Hedef</th>
                <th className="py-2 pr-4">Pozisyon Büyüklüğü</th>
                <th className="py-2 pr-4">PnL</th>
                <th className="py-2 pr-4">Nasıl Kapandı</th>
                <th className="py-2 pr-4">Kapandı</th>
              </tr>
            </thead>
            <tbody>
              {filteredTrades.map((t) => (
                <tr key={t.id} className="border-t border-line-soft">
                  <td className="py-2 pr-4 font-mono text-ink">
                    {onSelectSymbol ? (
                      <button
                        onClick={() => onSelectSymbol(t.symbol)}
                        className="hover:underline hover:text-accent transition-colors"
                        title={`${t.symbol} grafiğini aç`}
                      >
                        {t.symbol}
                      </button>
                    ) : (
                      t.symbol
                    )}
                    {t.timeframe && MEDIUM_TERM_TIMEFRAMES.has(t.timeframe) && (
                      <span className="ml-1"><Badge tone="accent">orta vadeli</Badge></span>
                    )}
                  </td>
                  <td className="py-2 pr-4">
                    <Badge tone={t.direction === "LONG" ? "rise" : "fall"}>{t.direction}</Badge>
                    {t.leverage && t.leverage > 1 && (
                      <span className="ml-1 text-xs text-accent font-medium">{t.leverage}x</span>
                    )}
                  </td>
                  <td className="py-2 pr-4 font-mono text-ink-soft">{format(t.entry_price)}</td>
                  <td className="py-2 pr-4 font-mono text-ink-soft">{format(t.exit_price)}</td>
                  <td className="py-2 pr-4 font-mono text-xs">
                    <span className="text-fall">{format(t.stop_loss_price)}</span>
                    {" / "}
                    <span className="text-rise">{format(t.take_profit_price)}</span>
                    {t.liquidation_price != null && (
                      <div className="text-fall/70 mt-0.5">likidasyon: {format(t.liquidation_price)}</div>
                    )}
                  </td>
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
