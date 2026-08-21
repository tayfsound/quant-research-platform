"""Strategy × Regime Compatibility'nin girdisini GERÇEK kapanmış
kararlardan toplayan tek kaynak — Faz 338 (MetaStrategyAgent v1).
analytics/strategy_regime_compatibility.py saf (pure) kalıyor, gerçek
veriye dokunan kod burada.

"strategy" etiketi: pump_fade_v1 experiment_bucket'ı "pump_fade", geri
kalan HER ŞEY (AI council + dormant multi_timeframe_cascade_v1 A/B
deneyi dahil) "ai_council" — v1'de kasıtlı olarak kaba/basit, tek
gerçek mekanik/izole strateji (pump_fade) ile council'in geri kalanını
ayırt etmek yeterli.

Faz 342 — kullanıcı bulgusu ("short pozisyonlar neden karlı değil?")
+ harici bir AI incelemesinin en önemli iddiası (bearish_low council
için kara delik): rejim TEK BAŞINA yeterli değil, aynı rejimde LONG/
SHORT davranışı dramatik farklı olabiliyor (gerçek örnek: SHORT/
bearish_low %8.3 isabet vs LONG/bearish_low %95.2). Bu yüzden
"strategy" etiketine YÖN de eklendi ("ai_council_LONG"/"ai_council_
SHORT"/"pump_fade_SHORT") — analytics/strategy_regime_compatibility.py
DEĞİŞMEDİ (zaten strategy×regime saf fonksiyonu), sadece etiketleme
inceltildi, hiçbir gate'e bağlı değil, hâlâ ölçüm-only.

Faz 345 — kullanıcının "joint örüntü tanıma" vizyonunun ("Scalp %99
başarılı bu koşullarda, örüntüyü tanıyabilirse büyük olay") gerçekçi,
kanıtlanabilir ilk adımı: tam 9-ajan kombinasyon uzayı (2⁹=512 hücre,
~1600 işlemle aşırı uydurmaya açık — bkz. agent_combination_
reliability.py'nin BİLEREK ikiliyle sınırlı kalma gerekçesi) yerine,
council etiketine trade_type (scalp/swing — api/rest/positions.py::
_classify_trade_type ile AYNI stop-mesafesi eşiği, %4.5) eklenip uzay
~50-60 hücreye indiriliyor. SADECE ai_council için anlamlı (pump_fade/
basis_arb zaten kendi sabit stop-geometrisiyle mekanik, trade_type
ayrımı bilgi katmıyor) — o yüzden SADECE council etiketine ekleniyor.
Ayrıca basis_arb_v1 artık kendi ayrı temel etiketini alıyor (önceden
yanlışlıkla "ai_council"a düşüyordu — gerçek agent oyu olmayan mekanik
bir strateji, council'le karıştırılmamalı)."""
from services.basis_arbitrage_strategy import EXPERIMENT_BUCKET as BASIS_ARB_EXPERIMENT_BUCKET
from services.pump_fade_strategy import EXPERIMENT_BUCKET as PUMP_FADE_EXPERIMENT_BUCKET

MAX_DECISIONS = 5000

# api/rest/positions.py::_SCALP_MAX_STOP_PCT ile AYNI eşik — tek bir
# kaynak yerine sabit tekrarı, o modülün import zincirini (FastAPI
# router) buraya taşımamak için kasıtlı.
_SCALP_MAX_STOP_PCT = 4.5


def _trade_type(entry_price: float | None, stop_loss_price: float | None) -> str | None:
    if entry_price is None or stop_loss_price is None or entry_price == 0:
        return None
    pct = abs(entry_price - stop_loss_price) / entry_price * 100
    return "scalp" if pct < _SCALP_MAX_STOP_PCT else "swing"


def _strategy_label(
    experiment_bucket: str | None, direction: str | None,
    entry_price: float | None, stop_loss_price: float | None,
) -> str:
    if experiment_bucket == PUMP_FADE_EXPERIMENT_BUCKET:
        base = "pump_fade"
    elif experiment_bucket == BASIS_ARB_EXPERIMENT_BUCKET:
        base = "basis_arb"
    else:
        base = "ai_council"

    direction_suffix = (direction or "").upper()
    label = f"{base}_{direction_suffix}" if direction_suffix in ("LONG", "SHORT") else base

    if base == "ai_council":
        trade_type = _trade_type(entry_price, stop_loss_price)
        if trade_type:
            label = f"{label}_{trade_type}"

    return label


def gather_strategy_regime_compatibility() -> dict:
    from database.session_factory import SessionFactory
    from sqlalchemy import text

    with SessionFactory.get_session() as session:
        rows = session.execute(
            text(
                """
                SELECT experiment_bucket, market_regime, direction, pnl, entry_price, stop_loss_price
                FROM decisions
                WHERE status = 'closed' AND excluded_from_stats = false
                  AND market_regime IS NOT NULL
                ORDER BY closed_at DESC
                LIMIT :limit
                """
            ),
            {"limit": MAX_DECISIONS},
        ).fetchall()

    records = [
        {
            "strategy": _strategy_label(r.experiment_bucket, r.direction, r.entry_price, r.stop_loss_price),
            "market_regime": r.market_regime,
            "win": (r.pnl or 0.0) > 0,
        }
        for r in rows
    ]

    from analytics.strategy_regime_compatibility import compute_strategy_regime_compatibility

    result = compute_strategy_regime_compatibility(records)
    return {"by_strategy": result, "n_decisions_analyzed": len(records)}
