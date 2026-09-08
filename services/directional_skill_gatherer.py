"""Yön Becerisi Toplayıcısı — Faz 458 (2026-09-09).

`analytics/directional_skill.py`'nin saf fonksiyonlarını GERÇEK
`decisions` verisine bağlar. `services/direction_calibration_gatherer.py`
(Faz 446) ile AYNI LATERAL JOIN desenini kullanır — o modülün yerine
GEÇMEZ, yanına eklenir: 446 "Brier/ECE kaç" sorusunu, bu modül "o Brier
NEREDEN geliyor ve anlamlı mı" sorusunu cevaplıyor.

446'DAN İKİ KASITLI FARK VAR:

1) `status = 'closed'` FİLTRESİ YOK. 446 sadece açılıp KAPANMIŞ kararları
   ölçüyor; ama yön becerisi TAHMİNİN özelliğidir, işlemin değil. Kapanma
   şartı koymak, kararı üç kez süzülmüş (EV kapısı + risk + bariyer) bir
   alt kümeye indirger ve tam da bu oturumun ana temasını (outcome ile
   direction'ı karıştırmak) tekrarlar. Burada YÖNLÜ HER KARAR ölçülüyor;
   pozisyona dönüşmüş olması aranmıyor.

2) `day` alanı taşınıyor — `compute_daily_sign_test()` örtüşen örneklem
   itirazını aşmak için günleri bağımsız gözlem sayıyor (123 sembol aynı
   piyasa hareketini paylaştığı için ham n=8.927 yanıltıcı derecede
   büyük).

Kasıtlı olarak SADECE rapor — hiçbir Celery görevi/beat kaydı YOK,
hiçbir canlı karar yolundan çağrılmıyor (Faz 446 ile AYNI desen).
"""
from datetime import timedelta

from analytics.calibration_uncertainty import compute_expected_calibration_error
from analytics.direction_prediction_v2 import compute_brier_score
from analytics.directional_skill import (
    compute_benchmark_relative_skill,
    compute_daily_sign_test,
    compute_murphy_decomposition,
    compute_pesaran_timmermann,
)
from analytics.evaluation_cohort import describe_evaluation_window
from analytics.forward_direction import DEFAULT_THRESHOLD_PCT, label_forward_direction
from services.pump_fade_strategy import EXPERIMENT_BUCKET as PUMP_FADE_EXPERIMENT_BUCKET

MAX_DECISIONS = 20000
DEFAULT_HORIZON = timedelta(hours=1)
DEFAULT_TOLERANCE_MINUTES = 5.0
# Faz 457'de kaldırılan Multi-Timeframe Cascade A/B deneyi hem control
# hem treatment kolunda kararları etiketlemişti; o dönemin verisi farklı
# bir mekanizmadan geldiği için yön ölçümünü kirletir (aynı gerekçe:
# services/asset_class_performance_gatherer.py).
MULTI_TIMEFRAME_CASCADE_PREFIX = "multi_timeframe_cascade_v1"


def gather_directional_skill(
    horizon: timedelta = DEFAULT_HORIZON,
    tolerance_minutes: float = DEFAULT_TOLERANCE_MINUTES,
    threshold_pct: float = DEFAULT_THRESHOLD_PCT,
    lookback_days: int = 21,
) -> dict:
    from sqlalchemy import text

    from database.session_factory import SessionFactory

    tolerance = timedelta(minutes=tolerance_minutes)
    with SessionFactory.get_session() as session:
        rows = session.execute(
            text("""
                SELECT d.confidence, d.direction, d.entry_price, d.timestamp,
                       d.timestamp::date AS day, ms.close AS price_at_horizon
                FROM decisions d
                JOIN LATERAL (
                    SELECT close FROM market_snapshots ms2
                    WHERE ms2.exchange = 'binance' AND ms2.symbol = d.symbol AND ms2.resolution = '1m'
                      AND ms2.time BETWEEN d.timestamp + :horizon - :tolerance
                                        AND d.timestamp + :horizon + :tolerance
                    ORDER BY abs(extract(epoch FROM (ms2.time - (d.timestamp + :horizon))))
                    LIMIT 1
                ) ms ON true
                WHERE d.excluded_from_stats = false
                  AND d.direction IN ('LONG', 'SHORT')
                  AND d.entry_price IS NOT NULL AND d.entry_price != 0
                  AND d.confidence IS NOT NULL
                  AND d.timestamp > now() - make_interval(days => :lookback_days)
                  AND (d.experiment_bucket IS NULL
                       OR (d.experiment_bucket != :exclude_bucket
                           AND d.experiment_bucket NOT LIKE :exclude_prefix))
                ORDER BY d.timestamp DESC
                LIMIT :limit
            """),
            {
                "horizon": horizon, "tolerance": tolerance,
                "exclude_bucket": PUMP_FADE_EXPERIMENT_BUCKET,
                "exclude_prefix": f"{MULTI_TIMEFRAME_CASCADE_PREFIX}%",
                "lookback_days": lookback_days, "limit": MAX_DECISIONS,
            },
        ).mappings().all()

    predictions: list[tuple[float, bool]] = []
    records: list[dict] = []
    neutral_count = 0
    for r in rows:
        forward_label = label_forward_direction(
            r["entry_price"], r["price_at_horizon"], threshold_pct,
        )
        if forward_label not in ("UP", "DOWN"):
            # NEUTRAL/None -> "yönü doğru mu bildi" sorusu anlamsız.
            # Sessizce atmak yerine SAYILIYOR: bu oran, eşiğin (%0,05)
            # veri için uygun olup olmadığının tek göstergesi.
            neutral_count += 1
            continue
        direction_correct = (
            (r["direction"] == "LONG" and forward_label == "UP")
            or (r["direction"] == "SHORT" and forward_label == "DOWN")
        )
        predictions.append((r["confidence"], direction_correct))
        records.append({
            "direction": r["direction"], "forward_label": forward_label, "day": r["day"],
        })

    return {
        # Faz 446'nın iki sayısı -- karşılaştırma sürekliliği için aynen
        # duruyor, artık YANLARINDA nereden geldikleri de var.
        "brier": compute_brier_score(predictions),
        "ece": compute_expected_calibration_error(predictions),
        # Faz 458'in üç yeni ölçümü.
        "murphy_decomposition": compute_murphy_decomposition(predictions),
        "benchmark_relative_skill": compute_benchmark_relative_skill(records),
        "pesaran_timmermann": compute_pesaran_timmermann(records),
        "daily_sign_test": compute_daily_sign_test(records),
        "horizon_minutes": round(horizon.total_seconds() / 60, 1),
        "threshold_pct": threshold_pct,
        "lookback_days": lookback_days,
        "n_directional": len(records),
        "n_neutral_excluded": neutral_count,
        "evaluation_window": describe_evaluation_window(
            [dict(r) for r in rows], limit=MAX_DECISIONS,
            exclude_experiment_buckets=[PUMP_FADE_EXPERIMENT_BUCKET],
        ),
    }
