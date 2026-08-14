import { useEffect, useMemo, useState } from "react";
import { authHeaders } from "../api/auth";
import { Card, PageHeader, Badge, EmptyState, StatCard, Button, ErrorNote, Spinner } from "../components/ui";
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
  current_price: number | null;
  net_unrealized_pnl: number | null;
  stop_loss_price: number | null;
  take_profit_price: number | null;
  leverage: number | null;
  liquidation_price: number | null;
  timeframe: string | null;
  pairs_trade: string | null;
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
  // Faz 268ae — kullanıcı isteği: kârlı gidip tersine dönen pozisyonlarda
  // stop girişe (başabaşa) çekiliyor; buna takılmak normal stop_loss'tan
  // (tam zarar) ayrı, "kayıptan kaçınıldı" anlamına geliyor.
  breakeven_stop: "Başabaş çekildi",
  time_expired: "Vadesi doldu",
  liquidation: "Likidasyon",
};

// Faz 268-sonrası — kullanıcı isteği: manuel kapatılan (exit_reason=
// "manual_full") işlemler ayrı bir "manuel" kovasında gösterilmesin,
// GERÇEK sonuçlarına göre (kârlıysa TP gibi, zarardaysa SL gibi)
// görüntülensin — kapanış mekanizması değil, gerçek kâr/zarar önemli.
// closed_trades_summary()'deki (backend) AYNI sınıflandırma mantığı.
function effectiveExitReason(exitReason: string | null, pnl: number | null): string | null {
  if (exitReason === "manual_full") {
    return (pnl ?? 0) > 0 ? "take_profit" : "stop_loss";
  }
  return exitReason;
}

// Faz 259: orta-vadeli katman kısa-vadeliden ayrı bir sinyal zaman dilimi
// kullanıyor (4h/1d) — dashboard'da hangi pozisyonun hangi katmandan
// geldiğini ayırt edebilmek için.
const MEDIUM_TERM_TIMEFRAMES = new Set(["4h", "1d"]);

// Faz 268ad: kullanıcı isteği — "orta vadeli" etiketinin aynısı diğer
// işlem türleri için de (scalp/swing) yapılsın, ayrıca hedge işlemler de
// görünür olsun. Kısa-vadeli katmanın SİNYAL zaman dilimi hep "5m" (trade_
// horizon ayarından etkilenmiyor) — o yüzden Scalp/Gün içi/Swing ayrımı
// timeframe alanından çıkarılamıyor. Bunun yerine pozisyonun GERÇEK stop
// mesafesinden (|entry - stop| / entry) sınıflandırılıyor — bu, açılış
// anında hangi risk tabanının (1h/4h/1d ATR) kullanıldığını doğrudan
// yansıtıyor ve trade_horizon ayarı sonradan değişse bile geçmiş
// pozisyonların etiketi bozulmuyor. Eşikler (%4.5 / %9) gerçek kapanmış
// işlem verisindeki kümelerden kalibre edildi (~%4 scalp, ~%5-8 gün içi,
// ~%14 swing kümeleri net ayrışıyor).
function tradeTypeBadge(
  p: Pick<Position, "timeframe" | "entry_price" | "stop_loss_price" | "pairs_trade">
): { label: string; tone: "accent" | "warn" | "neutral"; title?: string } | null {
  if (p.pairs_trade) {
    return { label: "hedge", tone: "warn", title: `Pairs trade: ${p.pairs_trade}` };
  }
  if (p.timeframe && MEDIUM_TERM_TIMEFRAMES.has(p.timeframe)) {
    return { label: "orta vadeli", tone: "accent" };
  }
  if (p.entry_price != null && p.stop_loss_price != null && p.entry_price !== 0) {
    const pct = (Math.abs(p.entry_price - p.stop_loss_price) / p.entry_price) * 100;
    if (pct < 4.5) return { label: "scalp", tone: "neutral" };
    if (pct < 9) return { label: "gün içi", tone: "neutral" };
    return { label: "swing", tone: "neutral" };
  }
  return null;
}

function fmt(n: number | null | undefined, digits = 2) {
  return n === null || n === undefined ? "—" : n.toFixed(digits);
}

// Faz 268-sonrası — kullanıcı isteği: "hangi ajandan ne karar geldiğini
// gösteren açıklayan bir fonksiyon." decisions.agent_contributions'ta
// zaten kayıtlı olan veriyi GET /positions/{id}/explain ayrıştırıp
// döndürüyor — burada Tokens.tsx'in kaldıraç modalıyla AYNI overlay
// deseni (fixed inset-0 + Card) kullanılıyor, tasarım tutarlılığı için.
type ExplainVote = {
  domain: string;
  direction: string;
  confidence: number;
  effective_influence: number | null;
  performance_weight: number | null;
  evidence: string[];
  caveats: string[];
};

type ExplainData = {
  id: string;
  symbol: string;
  final_direction: string;
  final_confidence: number | null;
  agent_votes: ExplainVote[];
  council_belief: Record<string, unknown> | null;
  debate_result: Record<string, unknown> | null;
  inner_critic: { risk_flags?: string[]; objections?: string[] } | null;
  decision_fusion: Record<string, unknown>[];
  weight_snapshot_id: string | null;
};

function ExplainModal({ decisionId, onClose }: { decisionId: string; onClose: () => void }) {
  const [data, setData] = useState<ExplainData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetch(`/api/v1/positions/${decisionId}/explain`, { headers: authHeaders() })
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(setData)
      .catch((e) => setError(String(e.message || e)))
      .finally(() => setLoading(false));
  }, [decisionId]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="w-full max-w-2xl max-h-[85vh] overflow-y-auto">
        <Card>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-ink">
              {data ? `${data.symbol} — karar açıklaması` : "Karar açıklaması"}
            </h3>
            <button onClick={onClose} className="text-ink-faint hover:text-ink text-lg leading-none px-1">×</button>
          </div>

          {loading && (
            <div className="flex items-center gap-2 text-sm text-ink-soft py-4">
              <Spinner /> Yükleniyor…
            </div>
          )}
          {error && <ErrorNote>{error}</ErrorNote>}

          {data && !loading && (
            <div className="space-y-4">
              <div>
                <p className="text-xs text-ink-faint mb-1">Nihai karar</p>
                <div className="flex items-center gap-2">
                  <Badge tone={data.final_direction === "LONG" ? "rise" : data.final_direction === "SHORT" ? "fall" : "neutral"}>
                    {data.final_direction}
                  </Badge>
                  {data.final_confidence != null && (
                    <span className="text-xs text-ink-soft">güven: {(data.final_confidence * 100).toFixed(1)}%</span>
                  )}
                </div>
              </div>

              <div>
                <p className="text-xs text-ink-faint mb-2">Ajan oyları ({data.agent_votes.length})</p>
                {data.agent_votes.length === 0 ? (
                  <p className="text-xs text-ink-faint">Kayıtlı ajan oyu yok.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-left text-ink-faint uppercase tracking-wide">
                          <th className="py-1 pr-3">Ajan</th>
                          <th className="py-1 pr-3">Yön</th>
                          <th className="py-1 pr-3">Güven</th>
                          <th className="py-1 pr-3">Etki</th>
                          <th className="py-1 pr-3">Kanıt / Not</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.agent_votes.map((v, i) => (
                          <tr key={i} className="border-t border-line-soft align-top">
                            <td className="py-1.5 pr-3 font-medium text-ink whitespace-nowrap">{v.domain}</td>
                            <td className="py-1.5 pr-3">
                              <Badge tone={v.direction === "LONG" ? "rise" : v.direction === "SHORT" ? "fall" : "neutral"}>
                                {v.direction}
                              </Badge>
                            </td>
                            <td className="py-1.5 pr-3 font-mono text-ink-soft">{(v.confidence * 100).toFixed(0)}%</td>
                            <td className="py-1.5 pr-3 font-mono text-ink-soft">
                              {v.effective_influence != null ? v.effective_influence.toFixed(3) : "—"}
                            </td>
                            <td className="py-1.5 pr-3 text-ink-soft">
                              {v.evidence?.map((e, j) => <div key={`e${j}`}>{e}</div>)}
                              {v.caveats?.map((c, j) => <div key={`c${j}`} className="text-ink-faint">⚠ {c}</div>)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {data.inner_critic && ((data.inner_critic.risk_flags?.length ?? 0) > 0 || (data.inner_critic.objections?.length ?? 0) > 0) && (
                <div>
                  <p className="text-xs text-ink-faint mb-1">İç eleştiri (InnerCritic)</p>
                  <div className="flex flex-wrap gap-1 mb-1">
                    {data.inner_critic.risk_flags?.map((f, i) => <Badge key={i} tone="warn">{f}</Badge>)}
                  </div>
                  {data.inner_critic.objections?.map((o, i) => (
                    <p key={i} className="text-xs text-ink-soft">{o}</p>
                  ))}
                </div>
              )}

              {data.decision_fusion.length > 0 && (
                <div>
                  <p className="text-xs text-ink-faint mb-1">Karar sentezi notları</p>
                  {data.decision_fusion.map((entry, i) => (
                    <p key={i} className="text-xs text-ink-soft font-mono break-all">{JSON.stringify(entry)}</p>
                  ))}
                </div>
              )}

              {data.debate_result && (
                <div>
                  <p className="text-xs text-ink-faint mb-1">Tartışma sonucu</p>
                  <p className="text-xs text-ink-soft">
                    {String((data.debate_result as { reasoning?: string }).reasoning ?? JSON.stringify(data.debate_result))}
                  </p>
                </div>
              )}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
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
  const [summary, setSummary] = useState<{ count: number; win_rate: number; total_pnl: number; tp_count: number; sl_count: number; manual_count: number } | null>(null);
  const [sinceMinutes, setSinceMinutes] = useState<number | null>(null);
  const [closingId, setClosingId] = useState<string | null>(null);
  const [closeError, setCloseError] = useState<string | null>(null);
  const [closingProfitable, setClosingProfitable] = useState(false);
  const [closeProfitableResult, setCloseProfitableResult] = useState<string | null>(null);
  const [explainId, setExplainId] = useState<string | null>(null);
  const { format, currency } = useCurrency();

  // Faz 268y — kullanıcı bulgusu: "ilk 98 işleme baktım... diğerlerini
  // göremiyorum." Açık pozisyon listesi hep en yeni 100'le sabitliydi
  // (limit var ama offset yoktu) — 869 pozisyondan sadece ilki
  // görülebiliyordu. Gerçek sayfalama: sayfa değişince backend'e offset
  // ile yeniden istek atılıyor.
  const OPEN_PAGE_SIZE = 100;
  const [openPage, setOpenPage] = useState(0);

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
    const offset = openPage * OPEN_PAGE_SIZE;
    fetch(`/api/v1/positions?limit=${OPEN_PAGE_SIZE}&offset=${offset}`, { headers: authHeaders() })
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openPage]);

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

  // Faz 268p — kullanıcı isteği: "kârdaki pozisyonları toplu kapatma
  // butonu... komisyona ezilmeyecek şekilde karda ise kapansınlar."
  // Backend zaten kapatmadan ÖNCE filtreliyor (services/position_closer.
  // py::estimate_net_pnl_if_closed_now) — burada sadece tetikliyoruz.
  const closeProfitablePositions = async () => {
    setCloseError(null);
    setCloseProfitableResult(null);
    setClosingProfitable(true);
    try {
      const res = await fetch("/api/v1/positions/close-profitable", {
        method: "POST",
        headers: authHeaders(),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `İstek başarısız oldu (${res.status})`);
      }
      const data = await res.json();
      setCloseProfitableResult(
        `${data.closed_count} pozisyon kapatıldı (komisyon sonrası net kârlı) — ${data.skipped_unprofitable} zararda/nötr olduğu için atlandı.`
      );
      load();
    } catch (err) {
      setCloseError(err instanceof Error ? err.message : "Toplu kapatma başarısız oldu.");
    } finally {
      setClosingProfitable(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Transactions"
        description="AI'ın gerçekten açtığı ve kapattığı paper-trading işlemleri."
      />

      <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-6">
        <StatCard label="Açık pozisyon" value={openSummary?.open_count ?? open.length} />
        <StatCard label="Kapanmış işlem" value={summary?.count ?? 0} sub={summary ? `%${(summary.win_rate * 100).toFixed(0)} kazanma oranı` : undefined} />
        <StatCard label="TP ile kapanan" value={summary?.tp_count ?? 0} tone="rise" />
        <StatCard label="SL ile kapanan" value={summary?.sl_count ?? 0} tone="fall" />
        <StatCard
          label={`Toplam PnL (kapanmış, ${currency})`}
          value={summary ? format(summary.total_pnl) : "—"}
          tone={summary && summary.total_pnl > 0 ? "rise" : summary && summary.total_pnl < 0 ? "fall" : "neutral"}
        />
      </div>

      <div className="flex items-center justify-between gap-4 mb-1">
        <h2 className="text-sm font-semibold text-ink-soft uppercase tracking-wide">Açık Pozisyonlar</h2>
        {open.length > 0 && (
          <Button
            variant="secondary"
            disabled={closingProfitable}
            onClick={closeProfitablePositions}
            className="!px-3 !py-1.5 text-xs"
          >
            {closingProfitable ? "Kapatılıyor…" : "Kârdakileri Toplu Kapat"}
          </Button>
        )}
      </div>
      {closeError && (
        <p className="text-xs text-fall mb-3">{closeError}</p>
      )}
      {closeProfitableResult && (
        <p className="text-xs text-ink-soft mb-3">{closeProfitableResult}</p>
      )}
      {openSummary && openSummary.open_count > OPEN_PAGE_SIZE && (
        <p className="text-xs text-ink-faint mb-3">
          {openPage * OPEN_PAGE_SIZE + 1}-{openPage * OPEN_PAGE_SIZE + open.length} / {openSummary.open_count}{" "}
          pozisyon gösteriliyor — altta sayfalarla gezebilirsiniz.
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
              {open.map((p) => {
                const badge = tradeTypeBadge(p);
                return (
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
                    {badge && (
                      <span className="ml-1" title={badge.title}><Badge tone={badge.tone}>{badge.label}</Badge></span>
                    )}
                    {/* Faz 268p — kullanıcı isteği: "pozisyon o an karda mı
                        zararda mı göremiyorum, sembol adının altında pnl
                        yazsın." Komisyon düşülmüş net rakam — "kârdakileri
                        toplu kapat" butonunun kullandığı AYNI sayı. */}
                    {p.net_unrealized_pnl != null ? (
                      <div className={`text-xs font-mono mt-0.5 ${p.net_unrealized_pnl > 0 ? "text-rise" : p.net_unrealized_pnl < 0 ? "text-fall" : "text-ink-faint"}`}>
                        {p.net_unrealized_pnl > 0 ? "+" : ""}{format(p.net_unrealized_pnl)}
                      </div>
                    ) : (
                      <div className="text-xs text-ink-faint mt-0.5">—</div>
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
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {openSummary && openSummary.open_count > OPEN_PAGE_SIZE && (
        <div className="flex items-center justify-center gap-3 mb-8 -mt-4">
          <Button
            variant="secondary"
            disabled={openPage === 0}
            onClick={() => setOpenPage((p) => Math.max(0, p - 1))}
            className="!px-3 !py-1.5 text-xs"
          >
            ← Önceki
          </Button>
          <span className="text-xs text-ink-faint">
            Sayfa {openPage + 1} / {Math.ceil(openSummary.open_count / OPEN_PAGE_SIZE)}
          </span>
          <Button
            variant="secondary"
            disabled={(openPage + 1) * OPEN_PAGE_SIZE >= openSummary.open_count}
            onClick={() => setOpenPage((p) => p + 1)}
            className="!px-3 !py-1.5 text-xs"
          >
            Sonraki →
          </Button>
        </div>
      )}

      <h2 className="text-sm font-semibold text-ink-soft uppercase tracking-wide mb-1">Kapanmış İşlemler</h2>
      {summary && summary.count > trades.length && (
        <p className="text-xs text-ink-faint mb-3">
          En son {trades.length} işlem gösteriliyor (toplam {summary.count} — üstteki özet kutuları
          her zaman gerçek toplamı yansıtır).
        </p>
      )}

      {/* Faz 268-sonrası — kullanıcı geri bildirimi: bu bölüm "sönük,
          sanki orada yokmuş gibi" görünüyordu (gri-gri üstüne gri) —
          diğer kartlarla (Card/.glass-panel) AYNI yüzen-panel deseni
          içine alındı, seçili olmayan pillerin de gerçek bir yüzeyi
          (bg-surface) var artık, arka planla karışmıyor. Tasarım
          bütünlüğü kullanıcının en öncelikli isteği. */}
      <Card className="mb-3">
        <div className="flex flex-wrap items-center gap-2">
          {SINCE_OPTIONS.map((opt) => (
            <button
              key={opt.label}
              onClick={() => setSinceMinutes(opt.minutes)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                sinceMinutes === opt.minutes
                  ? "bg-accent text-white border-accent shadow-layer-1"
                  : "bg-surface text-ink border-line shadow-sm hover:bg-surface-soft hover:border-accent/40"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </Card>

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
                <th className="py-2 pr-4"></th>
              </tr>
            </thead>
            <tbody>
              {filteredTrades.map((t) => {
                const badge = tradeTypeBadge(t);
                return (
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
                    {badge && (
                      <span className="ml-1" title={badge.title}><Badge tone={badge.tone}>{badge.label}</Badge></span>
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
                    {(() => {
                      const reason = effectiveExitReason(t.exit_reason, t.pnl);
                      if (!reason) return null;
                      return (
                        <Badge tone={reason === "take_profit" ? "rise" : (reason === "stop_loss" || reason === "liquidation") ? "fall" : "neutral"}>
                          {EXIT_REASON_LABELS[reason] || reason}
                        </Badge>
                      );
                    })()}
                  </td>
                  <td className="py-2 pr-4 text-ink-faint">{t.closed_at ? new Date(t.closed_at).toLocaleString() : "—"}</td>
                  <td className="py-2 pr-4">
                    <button
                      onClick={() => setExplainId(t.id)}
                      className="text-xs text-accent hover:underline"
                    >
                      Açıkla
                    </button>
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {explainId && <ExplainModal decisionId={explainId} onClose={() => setExplainId(null)} />}
    </div>
  );
}
