"""Varlık Sınıfı Performansı'nın girdisini GERÇEK kapanmış işlemlerden
toplayan tek kaynak. analytics/asset_class_performance.py saf kalıyor.

pump_fade_v1/basis_arb_v1 hariç — mekanik stratejiler, "AI ne kadar
başarılı" sorusuyla ilgisi yok (agent_combination_reliability/feature_ic
ile AYNI izolasyon).

Faz 367-devam — kullanıcı bulgusu (2026-08-27): "Kripto" kategorisinin
gerçek toplam PNL'i -$84,878 çıkmıştı, kullanıcı bunu pump_fade'in
bilinen ~$300K'lık tarihsel zararına bağladı — kontrol edildi, pump_fade
GERÇEKTEN sızmıyordu (0 satır) ama FARKLI bir kirlilik bulundu:
multi_timeframe_cascade_v1 (A/B deneyi, hem control hem treatment) TEK
BAŞINA -$90,428 kaybediyordu (23 Ağustos'ta yoğunlaşmış), gerçek "ai_
council" (deneysiz, experiment_bucket=None) kısmı aslında KÂRDA
(+$5,550). strategy_regime_compatibility_gatherer.py bu deneyi bilerek
"ai_council" etiketine dahil ediyor (rejim×strateji uyumu ölçümü için
savunulabilir bir tercih) — ama BU kart "gerçek AI performansı"nı
gösterdiğini iddia ettiği için deney/üretim ayrımı burada daha önemli,
kullanıcı onayıyla ayrı tutuluyor."""
from analytics.asset_class_performance import compute_asset_class_performance
from services.pump_fade_strategy import EXPERIMENT_BUCKET as PUMP_FADE_EXPERIMENT_BUCKET

MAX_DECISIONS = 5000
BASIS_ARB_EXPERIMENT_BUCKET = "basis_arb_v1"
# strategy_regime_compatibility_gatherer.py'nin BİLEREK "ai_council"a
# dahil ettiği A/B deneyi — bu kartın amacı farklı (üretim performansı),
# o yüzden burada AYRI tutuluyor.
MULTI_TIMEFRAME_CASCADE_PREFIX = "multi_timeframe_cascade_v1"


def _is_production_ai_council(experiment_bucket: str | None) -> bool:
    if experiment_bucket is None:
        return True
    return experiment_bucket != BASIS_ARB_EXPERIMENT_BUCKET and not experiment_bucket.startswith(
        MULTI_TIMEFRAME_CASCADE_PREFIX
    )


def gather_asset_class_performance() -> dict:
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        closed_trades = DecisionPersistor(session).list_closed_trades(
            limit=MAX_DECISIONS, exclude_experiment_bucket=PUMP_FADE_EXPERIMENT_BUCKET
        )
    closed_trades = [t for t in closed_trades if _is_production_ai_council(t.get("experiment_bucket"))]

    by_category = compute_asset_class_performance(closed_trades)
    return {"by_category": by_category, "n_trades_analyzed": len(closed_trades)}
