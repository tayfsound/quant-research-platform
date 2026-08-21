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
inceltildi, hiçbir gate'e bağlı değil, hâlâ ölçüm-only."""
from services.pump_fade_strategy import EXPERIMENT_BUCKET as PUMP_FADE_EXPERIMENT_BUCKET

MAX_DECISIONS = 5000


def _strategy_label(experiment_bucket: str | None, direction: str | None) -> str:
    base = "pump_fade" if experiment_bucket == PUMP_FADE_EXPERIMENT_BUCKET else "ai_council"
    direction_suffix = (direction or "").upper()
    return f"{base}_{direction_suffix}" if direction_suffix in ("LONG", "SHORT") else base


def gather_strategy_regime_compatibility() -> dict:
    from database.session_factory import SessionFactory
    from sqlalchemy import text

    with SessionFactory.get_session() as session:
        rows = session.execute(
            text(
                """
                SELECT experiment_bucket, market_regime, direction, pnl
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
            "strategy": _strategy_label(r.experiment_bucket, r.direction),
            "market_regime": r.market_regime,
            "win": (r.pnl or 0.0) > 0,
        }
        for r in rows
    ]

    from analytics.strategy_regime_compatibility import compute_strategy_regime_compatibility

    result = compute_strategy_regime_compatibility(records)
    return {"by_strategy": result, "n_decisions_analyzed": len(records)}
