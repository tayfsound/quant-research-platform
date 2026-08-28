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
  trade_type: string | null;
  exit_reason: string | null;
  opened_at: string | null;
  closed_at: string | null;
  execution_mode: string | null;
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
  //
  // Faz 359 — kullanıcı bulgusu: "Başabaş çekildi" gerçek $0 civarı
  // beklentisi yaratıyordu ama pnl -$140 gibi büyük olabiliyordu (orijinal
  // kaybın yarısından azı olduğu için "başarılı" sayılıyordu — matematiksel
  // olarak doğru, isim yanlış). Backend artık bunu ASLA "breakeven_stop"
  // olarak üretmiyor (bkz. services/position_closer.py) — eski kayıtlar
  // hâlâ bu etiketi taşıdığı için görünüm burada kalıyor, ama dürüstçe.
  breakeven_stop: "Zarar azaltıldı (eski etiket)",
  reduced_loss_stop: "Zarar azaltıldı",
  // Faz 291 — kullanıcı bulgusu (gerçek CHIPUSDT örneği): trailing/breakeven
  // stop kâra doğru da taşınabiliyor (bkz. position_closer.py'nin üç yönlü
  // ayrımı) — "Stop oldu" etiketi bunu zarar sanıyordu, ayrı ve doğru etiket.
  trailing_stop_profit: "İz süren stop (kârda kapandı)",
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

// Faz 268ad: kullanıcı isteği — "orta vadeli" etiketinin aynısı diğer
// işlem türleri için de (scalp/swing) yapılsın, ayrıca hedge işlemler de
// görünür olsun. Kısa-vadeli katmanın SİNYAL zaman dilimi hep "5m" —
// o yüzden Scalp/Swing ayrımı timeframe alanından çıkarılamıyor. Bunun
// yerine pozisyonun GERÇEK stop mesafesinden (|entry - stop| / entry)
// sınıflandırılıyor — açılış anında hangi risk tabanının kullanıldığını
// doğrudan yansıtıyor, hiçbir ayara bağımlı değil (Faz 317'de bu tabanı
// seçen manuel "işlem vadesi" ayarı zaten kaldırıldı). Eşik (%4.5) gerçek
// kapanmış işlem verisindeki kümelerden kalibre edildi.
//
// Faz 317 — kullanıcı kararı: "gün içi" (%4.5-%9) ara kovası kaldırıldı.
// Gerçek veriyle doğrulandı: 419 "gün içi" işleminin TAMAMI 2026-08-06/14
// arası, %70'i manual_full (gerçek AI kararı değil), ortalama pozisyon
// büyüklüğü $27.73 — eski/kirli test verisi (o tarihten bu yana tek bir
// yeni "gün içi" işlem yok). Kullanıcı: "zaten işlem almıyormuş ölü
// yatırım." Geçmiş kirli satırlar migration faz317 ile excluded_from_
// stats=true işaretlendi (silinmedi).
//
// Faz 323 — kullanıcı bulgusu: "swing 6 gündür yeni işlem almıyor" +
// "scalp %100 başarılı görünüyor, mantıksız." Kök neden: "orta vadeli"
// (timeframe IN ('4h','1d')) kategorisi risk profiliyle değil HANGİ
// MEKANİZMANIN kararı verdiğiyle ilgili kırılgan bir ayrımdı — hem gerçek
// bir A/B deneyinden (multi_timeframe_cascade_v1) hem de candle_timeframe
// ayarının 6 gün yanlışlıkla 4h/1d'de kalmasından (Faz316) besleniyordu,
// scalp/swing'i o süre boyunca hiç yeni kayıt almadan dondurmuştu. Deney
// karşılaştırması zaten experiment_bucket üzerinden ayrı yapılıyor — bu
// üçüncü kategori tamamen kaldırıldı, artık HER işlem (deneyler dahil)
// SADECE gerçek stop mesafesine göre scalp/swing'e ayrılıyor.
function tradeTypeBadge(
  p: Pick<Position, "entry_price" | "stop_loss_price" | "pairs_trade" | "trade_type">
): { label: string; tone: "accent" | "warn" | "neutral" | "info"; title?: string } | null {
  // Kullanıcı bulgusu: "Pump-Fade ile açtığı işlem var mı Transactions'ta
  // göremedim." pump_fade_strategy.py'nin açtığı mekanik işlemler backend'de
  // trade_type="pump_fade" olarak geliyor — diğer sezgisel (stop mesafesi
  // tabanlı) sınıflandırmalardan ÖNCE kontrol edilmeli, aksi halde stop
  // mesafesi tesadüfen scalp/swing aralığına denk gelip kimliğini kaybeder.
  if (p.trade_type === "pump_fade") {
    return { label: "Pump-Fade", tone: "warn" };
  }
  // Faz 344 — Cross-Asset Arbitrage Engine, pump_fade ile AYNI desen:
  // diğer (stop mesafesi tabanlı) sınıflandırmalardan ÖNCE kontrol
  // edilmeli — bu strateji hiç stop set etmiyor, aksi halde "kimliksiz"
  // görünürdü.
  if (p.trade_type === "basis_arb") {
    return { label: "Basis Arb", tone: "info" };
  }
  if (p.pairs_trade) {
    return { label: "hedge", tone: "warn", title: `Pairs trade: ${p.pairs_trade}` };
  }
  if (p.entry_price != null && p.stop_loss_price != null && p.entry_price !== 0) {
    const pct = (Math.abs(p.entry_price - p.stop_loss_price) / p.entry_price) * 100;
    // Kullanıcı bulgusu: "scalp" de diğerleri gibi neutral kaldığı için
    // sönük görünüyordu — "orta_vadeli" (Faz 323'te kaldırıldı) boşa
    // çıkan accent tonuna taşındı, yeni bir renk eklenmedi.
    if (pct < 4.5) return { label: "scalp", tone: "accent" };
    // Kullanıcı bulgusu: "swing" diğer türler gibi neutral kaldığı için
    // sönük görünüyordu — kendi rengine (info) taşındı.
    return { label: "swing", tone: "info" };
  }
  return null;
}

function fmt(n: number | null | undefined, digits = 2) {
  return n === null || n === undefined ? "—" : n.toFixed(digits);
}

// Kullanıcı isteği: "işlemleri sürekli tamamen açık görüntülemek yerine
// tıklayınca balon gibi açılıp şişecek, ilk sayfaya girişte üzerine
// tıklayana kadar görüş alanına sığacak iki üç satırlık bir yapı —
// kapanan işlemlere gitmek için çok fazla kaydırma yapmak zorunda
// kalıyorum." Native <details>/<summary> — LLMCritic.tsx::ToolCallTrace
// ile AYNI desen (bu kod tabanında zaten kurulu bir alışkanlık),
// varsayılan kapalı: sadece sembol/yön/güncel fiyat/anlık PnL (2 satır)
// görünür, tıklayınca giriş/miktar/kaldıraç/stop-hedef/aşamalı kapama
// gibi geri kalan her şey açılır.
function OpenPositionRow({
  p, format, onSelectSymbol, closingId, onPartialClose, onExplain,
}: {
  p: Position;
  format: (n: number | null | undefined) => string;
  onSelectSymbol?: (symbol: string) => void;
  closingId: string | null;
  onPartialClose: (id: string, fraction: number) => void;
  onExplain: () => void;
}) {
  const badge = tradeTypeBadge(p);
  const pnl = p.net_unrealized_pnl;
  return (
    <details className="group border border-line-soft rounded-lg bg-canvas-soft open:bg-canvas open:shadow-sm">
      <summary className="cursor-pointer list-none px-3 py-2 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-ink-faint text-xs transition-transform group-open:rotate-90">▶</span>
          <span className="font-mono text-ink font-medium truncate">{p.symbol}</span>
          {badge && <Badge tone={badge.tone}>{badge.label}</Badge>}
          <Badge tone={p.direction === "LONG" ? "rise" : "fall"}>{p.direction}</Badge>
          {p.execution_mode === "testnet" && (
            <span title="Bu pozisyon simülasyon değil — gerçek Binance Futures Testnet emirleriyle açıldı/yönetiliyor.">
              <Badge tone="warn">testnet</Badge>
            </span>
          )}
        </div>
        <div className="flex items-center gap-4 shrink-0 text-xs">
          <span className="font-mono text-ink-soft hidden sm:inline">
            {p.current_price != null ? format(p.current_price) : "—"}
          </span>
          <span className={`font-mono font-medium ${pnl != null && pnl > 0 ? "text-rise" : pnl != null && pnl < 0 ? "text-fall" : "text-ink-faint"}`}>
            {pnl != null ? `${pnl > 0 ? "+" : ""}${format(pnl)}` : "—"}
          </span>
        </div>
      </summary>

      <div className="px-3 pb-3 pt-1 border-t border-line-soft/60 grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-2 text-xs">
        <div>
          <div className="text-ink-faint">Giriş fiyatı</div>
          <div className="font-mono text-ink-soft">{format(p.entry_price)}</div>
        </div>
        <div>
          <div className="text-ink-faint">Miktar</div>
          <div className="font-mono text-ink-soft">{fmt(p.quantity, 4)}</div>
        </div>
        <div>
          <div className="text-ink-faint">Pozisyon büyüklüğü</div>
          <div className="font-mono text-ink-soft">
            {p.entry_price != null && p.quantity != null ? format(p.entry_price * p.quantity) : "—"}
          </div>
        </div>
        <div>
          <div className="text-ink-faint">Kaldıraç</div>
          {p.leverage && p.leverage > 1 ? (
            <Badge tone="accent">{p.leverage}x</Badge>
          ) : (
            <span className="text-ink-faint">spot</span>
          )}
        </div>
        <div>
          <div className="text-ink-faint">Stop / Hedef</div>
          <div className="font-mono">
            <span className="text-fall">{format(p.stop_loss_price)}</span>
            {" / "}
            <span className="text-rise">{format(p.take_profit_price)}</span>
          </div>
          {p.liquidation_price != null && (
            <div className="text-fall/70 font-mono mt-0.5">likidasyon: {format(p.liquidation_price)}</div>
          )}
        </div>
        <div>
          <div className="text-ink-faint">Açıldı</div>
          <div className="text-ink-soft">{p.opened_at ? new Date(p.opened_at).toLocaleString() : "—"}</div>
        </div>
        {p.realized_pnl != null && (
          <div>
            <div className="text-ink-faint">Realize edilen</div>
            <div className={`font-mono ${p.realized_pnl > 0 ? "text-rise" : p.realized_pnl < 0 ? "text-fall" : "text-ink-soft"}`}>
              {format(p.realized_pnl)}
            </div>
          </div>
        )}
        <div className="col-span-2 md:col-span-4 flex flex-wrap items-center gap-1.5 mt-1">
          {onSelectSymbol && (
            <button
              onClick={() => onSelectSymbol(p.symbol)}
              className="text-accent hover:underline mr-2"
            >
              {p.symbol} grafiğini aç
            </button>
          )}
          {PARTIAL_CLOSE_OPTIONS.map((opt) => (
            <Button
              key={opt.label}
              variant={opt.fraction === 1.0 ? "danger" : "secondary"}
              disabled={closingId === p.id}
              onClick={() => onPartialClose(p.id, opt.fraction)}
              className="!px-2 !py-1 text-xs"
            >
              {opt.label}
            </Button>
          ))}
          <button onClick={onExplain} className="text-accent hover:underline ml-auto">
            Açıkla
          </button>
        </div>
      </div>
    </details>
  );
}

function ClosedTradeRow({
  t, format, onSelectSymbol, onExplain,
}: {
  t: Position;
  format: (n: number | null | undefined) => string;
  onSelectSymbol?: (symbol: string) => void;
  onExplain: () => void;
}) {
  const badge = tradeTypeBadge(t);
  const reason = effectiveExitReason(t.exit_reason, t.pnl);
  return (
    <details className="group border border-line-soft rounded-lg bg-canvas-soft open:bg-canvas open:shadow-sm">
      <summary className="cursor-pointer list-none px-3 py-2 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-ink-faint text-xs transition-transform group-open:rotate-90">▶</span>
          <span className="font-mono text-ink font-medium truncate">{t.symbol}</span>
          {badge && <Badge tone={badge.tone}>{badge.label}</Badge>}
          <Badge tone={t.direction === "LONG" ? "rise" : "fall"}>{t.direction}</Badge>
          {reason && (
            <Badge tone={
              reason === "take_profit" || reason === "trailing_stop_profit" ? "rise"
              // Faz 359 — kullanıcı bulgusu: reduced_loss_stop/breakeven_stop
              // (eski etiket) HÂLÂ birer gerçek kayıp (sadece azaltılmış) —
              // stop_loss/liquidation'la AYNI kırmızı tonda gösterilmeli,
              // "neutral" (soluk) diğerleriyle karışıp kaybı gizlememeli.
              : (reason === "stop_loss" || reason === "liquidation" || reason === "reduced_loss_stop" || reason === "breakeven_stop") ? "fall"
              : "neutral"
            }>
              {EXIT_REASON_LABELS[reason] || reason}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-4 shrink-0 text-xs">
          <span className="text-ink-faint hidden sm:inline">
            {t.closed_at ? new Date(t.closed_at).toLocaleString() : "—"}
          </span>
          <span className={`font-mono font-medium ${t.pnl && t.pnl > 0 ? "text-rise" : t.pnl && t.pnl < 0 ? "text-fall" : "text-ink-soft"}`}>
            {format(t.pnl)}
          </span>
        </div>
      </summary>

      <div className="px-3 pb-3 pt-1 border-t border-line-soft/60 grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-2 text-xs">
        <div>
          <div className="text-ink-faint">Giriş</div>
          <div className="font-mono text-ink-soft">{format(t.entry_price)}</div>
        </div>
        <div>
          <div className="text-ink-faint">Çıkış</div>
          <div className="font-mono text-ink-soft">{format(t.exit_price)}</div>
        </div>
        <div>
          <div className="text-ink-faint">Stop / Hedef</div>
          <div className="font-mono">
            <span className="text-fall">{format(t.stop_loss_price)}</span>
            {" / "}
            <span className="text-rise">{format(t.take_profit_price)}</span>
          </div>
          {t.liquidation_price != null && (
            <div className="text-fall/70 font-mono mt-0.5">likidasyon: {format(t.liquidation_price)}</div>
          )}
        </div>
        <div>
          <div className="text-ink-faint">Pozisyon büyüklüğü</div>
          <div className="font-mono text-ink-soft">
            {t.entry_price != null && t.quantity != null ? format(t.entry_price * t.quantity) : "—"}
          </div>
        </div>
        <div>
          <div className="text-ink-faint">Kaldıraç</div>
          {t.leverage && t.leverage > 1 ? (
            <Badge tone="accent">{t.leverage}x</Badge>
          ) : (
            <span className="text-ink-faint">spot</span>
          )}
        </div>
        <div>
          <div className="text-ink-faint">Açıldı</div>
          <div className="text-ink-soft">{t.opened_at ? new Date(t.opened_at).toLocaleString() : "—"}</div>
        </div>
        <div>
          <div className="text-ink-faint">Kapandı</div>
          <div className="text-ink-soft">{t.closed_at ? new Date(t.closed_at).toLocaleString() : "—"}</div>
        </div>
        <div className="col-span-2 md:col-span-4 flex items-center gap-1.5 mt-1">
          {onSelectSymbol && (
            <button
              onClick={() => onSelectSymbol(t.symbol)}
              className="text-accent hover:underline mr-2"
            >
              {t.symbol} grafiğini aç
            </button>
          )}
          <button onClick={onExplain} className="text-accent hover:underline ml-auto">
            Açıkla
          </button>
        </div>
      </div>
    </details>
  );
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
  portfolio_confidence_discounts: {
    reason: string;
    confidence_before: number;
    confidence_after: number;
    multiplier: number;
    effective_number_of_bets?: number;
  }[];
};

const PORTFOLIO_DISCOUNT_REASON_LABELS: Record<string, string> = {
  same_direction_correlation: "Aynı yönde, birbirine yüksek korele semboller",
  low_effective_number_of_bets: "Portföyün genel çeşitlendirme kalitesi düşük (ENB)",
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
        <Card opaque>
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

              {data.portfolio_confidence_discounts.length > 0 && (
                <div className="bg-canvas-soft rounded-lg p-2.5 border border-line-soft">
                  <p className="text-xs text-ink-faint mb-1.5">
                    ⚠ Bu güven, ajan oylarından SONRA portföy seviyesinde düşürüldü
                  </p>
                  {data.portfolio_confidence_discounts.map((d, i) => (
                    <p key={i} className="text-xs text-ink-soft">
                      {PORTFOLIO_DISCOUNT_REASON_LABELS[d.reason] ?? d.reason}: %{(d.confidence_before * 100).toFixed(1)} → %
                      {(d.confidence_after * 100).toFixed(1)}
                      {d.effective_number_of_bets != null && ` (ENB: ${d.effective_number_of_bets.toFixed(2)})`}
                    </p>
                  ))}
                </div>
              )}

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

// Kullanıcı isteği: "pozisyon türüne göre filtreleyebileyim, sonra long/
// short durumuna göre, karda ya da zararda olanlara göre." tradeTypeBadge()
// zaten hem açık hem kapalı pozisyonlar için AYNI sınıflandırmayı
// üretiyor — filtre seçenekleri onunla BİREBİR aynı, ayrı bir taksonomi
// icat edilmedi.
type TypeFilter = "all" | "pump_fade" | "basis_arb" | "hedge" | "scalp" | "swing";
type DirectionFilter = "all" | "LONG" | "SHORT";
type OutcomeFilter = "all" | "profit" | "loss";
// Kullanıcı isteği (2026-08-28): "canlıdan gelen işlemler etiketlenecek
// mi, filtreleyebilecek miyim?" — etiket zaten vardı (execution_mode ===
// "testnet" rozeti, aşağıda), sadece filtre eksikti.
type ExecutionModeFilter = "all" | "testnet" | "simulated";

const TYPE_FILTER_OPTIONS: { value: TypeFilter; label: string }[] = [
  { value: "all", label: "Tüm türler" },
  { value: "pump_fade", label: "Pump-Fade" },
  { value: "basis_arb", label: "Basis Arb" },
  { value: "hedge", label: "Hedge" },
  { value: "scalp", label: "Scalp" },
  { value: "swing", label: "Swing" },
];

function matchesTypeFilter(p: Position, filter: TypeFilter): boolean {
  if (filter === "all") return true;
  const badge = tradeTypeBadge(p);
  const badgeKey = badge?.label === "Pump-Fade" ? "pump_fade"
    : badge?.label === "Basis Arb" ? "basis_arb"
    : badge?.label === "hedge" ? "hedge"
    : badge?.label === "scalp" ? "scalp"
    : badge?.label === "swing" ? "swing"
    : null;
  return badgeKey === filter;
}

function matchesDirectionFilter(p: Position, filter: DirectionFilter): boolean {
  return filter === "all" || p.direction === filter;
}

function matchesOutcomeFilter(pnl: number | null | undefined, filter: OutcomeFilter): boolean {
  if (filter === "all") return true;
  if (pnl == null) return false;
  return filter === "profit" ? pnl > 0 : pnl < 0;
}

function matchesExecutionModeFilter(p: Position, filter: ExecutionModeFilter): boolean {
  if (filter === "all") return true;
  if (filter === "testnet") return p.execution_mode === "testnet";
  // "simulated": execution_mode NULL/eksik de simülasyon sayılır (eski
  // satırlar, execution_mode sütunu Faz 315'ten önce hiç yoktu).
  return p.execution_mode !== "testnet";
}

function FilterSelect<T extends string>({
  value, onChange, options,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string }[];
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as T)}
      className="px-3 py-1.5 rounded-lg text-xs font-medium border border-line bg-surface text-ink shadow-sm focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent"
    >
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>{opt.label}</option>
      ))}
    </select>
  );
}

export default function Transactions({ onSelectSymbol }: { onSelectSymbol?: (symbol: string) => void } = {}) {
  const [open, setOpen] = useState<Position[]>([]);
  const [openSummary, setOpenSummary] = useState<{ open_count: number; committed_notional: number; profit_count: number; loss_count: number } | null>(null);
  const [trades, setTrades] = useState<Position[]>([]);
  const [summary, setSummary] = useState<{ count: number; win_rate: number; total_pnl: number; tp_count: number; sl_count: number; manual_count: number } | null>(null);
  const [sinceMinutes, setSinceMinutes] = useState<number | null>(null);
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");
  const [directionFilter, setDirectionFilter] = useState<DirectionFilter>("all");
  const [outcomeFilter, setOutcomeFilter] = useState<OutcomeFilter>("all");
  const [executionModeFilter, setExecutionModeFilter] = useState<ExecutionModeFilter>("all");
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

  // Faz 362-devam — kullanıcı isteği: "kör gidiyorum, geriye dönüp
  // inceleme yapamıyorum" — kapanmış işlemler de OPEN_PAGE_SIZE ile AYNI
  // desende, offset destekli GET /trades'e bağlandı (backend Faz 268y'nin
  // açık pozisyon sayfalamasıyla AYNI deseni izliyor).
  const TRADES_PAGE_SIZE = 100;
  const [tradesPage, setTradesPage] = useState(0);

  const hasActiveFilters = typeFilter !== "all" || directionFilter !== "all" || outcomeFilter !== "all" || executionModeFilter !== "all";

  const filteredTrades = useMemo(() => {
    let result = trades;
    if (sinceMinutes !== null) {
      const cutoff = sinceCutoffMs(sinceMinutes);
      result = result.filter((t) => t.closed_at && new Date(t.closed_at).getTime() >= cutoff);
    }
    return result.filter((t) =>
      matchesTypeFilter(t, typeFilter)
      && matchesDirectionFilter(t, directionFilter)
      && matchesOutcomeFilter(t.pnl, outcomeFilter)
      && matchesExecutionModeFilter(t, executionModeFilter)
    );
  }, [trades, sinceMinutes, typeFilter, directionFilter, outcomeFilter, executionModeFilter]);

  const filteredOpen = useMemo(() => {
    return open.filter((p) =>
      matchesTypeFilter(p, typeFilter)
      && matchesDirectionFilter(p, directionFilter)
      && matchesOutcomeFilter(p.net_unrealized_pnl, outcomeFilter)
      && matchesExecutionModeFilter(p, executionModeFilter)
    );
  }, [open, typeFilter, directionFilter, outcomeFilter, executionModeFilter]);

  const filteredSummary = useMemo(() => {
    if (sinceMinutes === null && !hasActiveFilters) return null;
    const wins = filteredTrades.filter((t) => (t.pnl ?? 0) > 0).length;
    const totalPnl = filteredTrades.reduce((sum, t) => sum + (t.pnl ?? 0), 0);
    return {
      count: filteredTrades.length,
      win_rate: filteredTrades.length ? wins / filteredTrades.length : 0,
      total_pnl: totalPnl,
    };
  }, [filteredTrades, sinceMinutes]);

  // Faz 354 — kullanıcı bulgusu: "50 küsür pump-fade işlemi dashboard
  // kartlarında görünüyor ama Transactions'ta filtrelediğimde sıfır
  // görüyorum." Kök neden: tür/yön/kâr-zarar filtresi (matchesTypeFilter
  // vb.) SADECE o an sayfalanmış `open` state'i üzerinde çalışıyordu —
  // pump-fade Ağustos 20'den sonra hiç yeni pozisyon açmadığı için (bkz.
  // pump_fade_enabled=false) tüm pump-fade satırları en-yeni-önce sırada
  // sayfa 1'in ÇOK gerisinde kalmıştı (794 açık pozisyonda sıra 612-668).
  // Bir filtre aktifken normal 100'lük sayfalamayı atlayıp TÜM açık
  // pozisyonları tek seferde çekiyoruz ki filtre gerçekten tüm veri
  // üzerinde çalışsın.
  const load = () => {
    const offset = hasActiveFilters ? 0 : openPage * OPEN_PAGE_SIZE;
    const limit = hasActiveFilters ? 5000 : OPEN_PAGE_SIZE;
    fetch(`/api/v1/positions?limit=${limit}&offset=${offset}`, { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => {
        setOpen(data.positions || []);
        setOpenSummary(data.summary || null);
      });
    const tradesOffset = hasActiveFilters ? 0 : tradesPage * TRADES_PAGE_SIZE;
    const tradesLimit = hasActiveFilters ? 5000 : TRADES_PAGE_SIZE;
    fetch(`/api/v1/trades?limit=${tradesLimit}&offset=${tradesOffset}`, { headers: authHeaders() })
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
  }, [openPage, tradesPage, hasActiveFilters]);

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
        {openSummary && openSummary.profit_count + openSummary.loss_count > 0 && (
          <StatCard
            label="Açık pozisyon: karda / zararda"
            value={
              <>
                <span className="text-rise">
                  %{(100 * openSummary.profit_count / (openSummary.profit_count + openSummary.loss_count)).toFixed(0)}
                </span>
                {" / "}
                <span className="text-fall">
                  %{(100 * openSummary.loss_count / (openSummary.profit_count + openSummary.loss_count)).toFixed(0)}
                </span>
              </>
            }
            sub={`${openSummary.profit_count} karda, ${openSummary.loss_count} zararda (tüm açık pozisyonlar, sadece bu sayfa değil)`}
          />
        )}
        <StatCard label="Kapanmış işlem" value={summary?.count ?? 0} sub={summary ? `%${(summary.win_rate * 100).toFixed(0)} kazanma oranı` : undefined} />
        <StatCard label="TP ile kapanan" value={summary?.tp_count ?? 0} tone="rise" />
        <StatCard label="SL ile kapanan" value={summary?.sl_count ?? 0} tone="fall" />
        <StatCard
          label={`Toplam PnL (kapanmış, ${currency})`}
          value={summary ? format(summary.total_pnl) : "—"}
          tone={summary && summary.total_pnl > 0 ? "rise" : summary && summary.total_pnl < 0 ? "fall" : "neutral"}
        />
      </div>

      {/* Kullanıcı isteği: "pozisyon türüne göre filtreleyebileyim, sonra
          long/short durumuna göre, karda ya da zararda olanlara göre."
          Hem açık pozisyonlar hem kapanmış işlemler listesini AYNI ANDA
          süzer — iki ayrı filtre seti kafa karıştırırdı. */}
      <Card className="mb-6">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-ink-faint font-medium mr-1">Filtrele:</span>
          <FilterSelect value={typeFilter} onChange={setTypeFilter} options={TYPE_FILTER_OPTIONS} />
          <FilterSelect
            value={directionFilter}
            onChange={setDirectionFilter}
            options={[
              { value: "all", label: "Yön: Tümü" },
              { value: "LONG", label: "LONG" },
              { value: "SHORT", label: "SHORT" },
            ]}
          />
          <FilterSelect
            value={outcomeFilter}
            onChange={setOutcomeFilter}
            options={[
              { value: "all", label: "Kâr/Zarar: Tümü" },
              { value: "profit", label: "Sadece kârda" },
              { value: "loss", label: "Sadece zararda" },
            ]}
          />
          <FilterSelect
            value={executionModeFilter}
            onChange={setExecutionModeFilter}
            options={[
              { value: "all", label: "Mod: Tümü" },
              { value: "testnet", label: "Sadece canlı (testnet)" },
              { value: "simulated", label: "Sadece simülasyon" },
            ]}
          />
          {hasActiveFilters && (
            <button
              onClick={() => { setTypeFilter("all"); setDirectionFilter("all"); setOutcomeFilter("all"); setExecutionModeFilter("all"); }}
              className="text-xs text-accent hover:underline ml-1"
            >
              Filtreleri temizle
            </button>
          )}
        </div>
      </Card>

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
      {filteredOpen.length === 0 ? (
        <EmptyState label={hasActiveFilters ? "Filtreye uyan açık pozisyon yok." : "Şu an açık pozisyon yok."} />
      ) : (
        <div className="flex flex-col gap-1.5 mb-8">
          {filteredOpen.map((p) => (
            <OpenPositionRow
              key={p.id}
              p={p}
              format={format}
              onSelectSymbol={onSelectSymbol}
              closingId={closingId}
              onPartialClose={partialClose}
              onExplain={() => setExplainId(p.id)}
            />
          ))}
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
      {summary && summary.count > TRADES_PAGE_SIZE && !hasActiveFilters && (
        <p className="text-xs text-ink-faint mb-3">
          {tradesPage * TRADES_PAGE_SIZE + 1}-{tradesPage * TRADES_PAGE_SIZE + trades.length} / {summary.count}{" "}
          işlem gösteriliyor — altta sayfalarla gezebilirsiniz (üstteki özet kutuları her zaman gerçek
          toplamı yansıtır).
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
        <div className="flex flex-col gap-1.5">
          {filteredTrades.map((t) => (
            <ClosedTradeRow
              key={t.id}
              t={t}
              format={format}
              onSelectSymbol={onSelectSymbol}
              onExplain={() => setExplainId(t.id)}
            />
          ))}
        </div>
      )}

      {summary && summary.count > TRADES_PAGE_SIZE && !hasActiveFilters && (
        <div className="flex items-center justify-center gap-3 mt-4 mb-8">
          <Button
            variant="secondary"
            disabled={tradesPage === 0}
            onClick={() => setTradesPage((p) => Math.max(0, p - 1))}
            className="!px-3 !py-1.5 text-xs"
          >
            ← Önceki
          </Button>
          <span className="text-xs text-ink-faint">
            Sayfa {tradesPage + 1} / {Math.ceil(summary.count / TRADES_PAGE_SIZE)}
          </span>
          <Button
            variant="secondary"
            disabled={(tradesPage + 1) * TRADES_PAGE_SIZE >= summary.count}
            onClick={() => setTradesPage((p) => p + 1)}
            className="!px-3 !py-1.5 text-xs"
          >
            Sonraki →
          </Button>
        </div>
      )}

      {explainId && <ExplainModal decisionId={explainId} onClose={() => setExplainId(null)} />}
    </div>
  );
}
