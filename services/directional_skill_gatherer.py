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

2) `entry_price` YERİNE, karar anındaki GERÇEK piyasa fiyatı referans
   alınıyor (`COALESCE(entry_price, karar-anı-snapshot)`). Faz 459'da
   ölçüldü: son 21 günde 115.701 yönlü kararın yalnızca 10.450'si (%9)
   pozisyona dönüşmüş; kalan 105.251'inin `entry_price`'ı NULL. Yani
   `entry_price IS NOT NULL` şartı, farkında olmadan "tüm kapılardan
   geçmiş" %9'luk alt kümeyi seçiyordu -- Faz 441/446/458 dahil bugüne
   kadarki BÜTÜN yön ölçümlerimiz bu kör noktadaydı.

3) `day` alanı taşınıyor — `compute_daily_sign_test()` örtüşen örneklem
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
    compute_execution_selection_effect,
    compute_murphy_decomposition,
    compute_pesaran_timmermann,
)
from analytics.evaluation_cohort import describe_evaluation_window
from analytics.feature_directional_value import compute_feature_directional_value
from analytics.forward_direction import DEFAULT_THRESHOLD_PCT, label_forward_direction
from analytics.reversal_conditioning import compute_conditional_direction_value
from analytics.signal_directional_value import compute_signal_directional_value
from services.pump_fade_strategy import EXPERIMENT_BUCKET as PUMP_FADE_EXPERIMENT_BUCKET

MAX_DECISIONS = 20000
DEFAULT_HORIZON = timedelta(hours=1)
DEFAULT_TOLERANCE_MINUTES = 5.0
DEFAULT_PRIOR_WINDOW_MINUTES = 15.0
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
    prior_window_minutes: float = DEFAULT_PRIOR_WINDOW_MINUTES,
) -> dict:
    from sqlalchemy import text

    from database.session_factory import SessionFactory

    tolerance = timedelta(minutes=tolerance_minutes)
    prior_window = timedelta(minutes=prior_window_minutes)
    with SessionFactory.get_session() as session:
        rows = session.execute(
            text("""
                SELECT d.confidence, d.direction, d.timestamp,
                       d.timestamp::date AS day,
                       -- Faz 459: açılmayan kararların entry_price'ı NULL;
                       -- referans olarak karar anındaki gerçek piyasa
                       -- fiyatı kullanılıyor (bkz. modül notu 2).
                       COALESCE(d.entry_price, ref.close) AS reference_price,
                       (d.opened_at IS NOT NULL) AS executed,
                       d.market_regime, d.agent_contributions,
                       ms.close AS price_at_horizon,
                       prv.close AS price_before
                FROM decisions d
                -- LEFT: entry_price ZATEN varsa (açılmış karar) karar-anı
                -- snapshot'ı olmasa da kayıt ölçülebilir olmalı; INNER
                -- yapmak açılmış kararların bir kısmını sessizce düşürürdü.
                LEFT JOIN LATERAL (
                    SELECT close FROM market_snapshots ms0
                    WHERE ms0.exchange = 'binance' AND ms0.symbol = d.symbol AND ms0.resolution = '1m'
                      AND ms0.time BETWEEN d.timestamp - :tolerance AND d.timestamp + :tolerance
                    ORDER BY abs(extract(epoch FROM (ms0.time - d.timestamp)))
                    LIMIT 1
                ) ref ON true
                JOIN LATERAL (
                    SELECT close FROM market_snapshots ms2
                    WHERE ms2.exchange = 'binance' AND ms2.symbol = d.symbol AND ms2.resolution = '1m'
                      AND ms2.time BETWEEN d.timestamp + :horizon - :tolerance
                                        AND d.timestamp + :horizon + :tolerance
                    ORDER BY abs(extract(epoch FROM (ms2.time - (d.timestamp + :horizon))))
                    LIMIT 1
                ) ms ON true
                -- Faz 459: kararın HEMEN ÖNCESİNDEKİ fiyat. LEFT JOIN --
                -- eksikse kayıt yön ölçümünden DÜŞMEMELİ, sadece dönüş
                -- tabakalamasına giremez (fail-closed, bkz. gatherer notu).
                LEFT JOIN LATERAL (
                    SELECT close FROM market_snapshots ms3
                    WHERE ms3.exchange = 'binance' AND ms3.symbol = d.symbol AND ms3.resolution = '1m'
                      AND ms3.time BETWEEN d.timestamp - :prior_window - :tolerance
                                        AND d.timestamp - :prior_window + :tolerance
                    ORDER BY abs(extract(epoch FROM (ms3.time - (d.timestamp - :prior_window))))
                    LIMIT 1
                ) prv ON true
                WHERE d.excluded_from_stats = false
                  AND d.direction IN ('LONG', 'SHORT')
                  AND d.confidence IS NOT NULL
                  AND COALESCE(d.entry_price, ref.close) > 0
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
                "prior_window": prior_window,
                "lookback_days": lookback_days, "limit": MAX_DECISIONS,
            },
        ).mappings().all()

    predictions: list[tuple[float, bool]] = []
    records: list[dict] = []
    # Faz 460: sinyal seviyesi. agent_contributions'daki
    # feature_contributions BUGÜNE KADAR ORADAYDI, hiç bu amaçla
    # okunmamıştı -- yeni kayıt/wiring gerekmiyor.
    signal_records: list[dict] = []
    # Faz 462: ctx.market.features'taki 40+ ham özellik. Faz 411/423/436/
    # 437/438/439/461'de "önce gözlemle" diye eklendiler, veri birikti
    # ama HİÇ ölçülmediler.
    feature_records: list[dict] = []
    neutral_count = 0
    for r in rows:
        forward_label = label_forward_direction(
            r["reference_price"], r["price_at_horizon"], threshold_pct,
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
        # Faz 459 -- dönüş tabakalaması için karar öncesi getiri.
        # price_before yoksa None kalır: `bucket_prior_return()` bunu
        # fail-closed dışlar, kayıt yön ölçümünde YİNE DE sayılır.
        prior_return = None
        if r["price_before"] and r["price_before"] > 0:
            prior_return = (r["reference_price"] - r["price_before"]) / r["price_before"]
        records.append({
            "direction": r["direction"], "forward_label": forward_label, "day": r["day"],
            "prior_return": prior_return, "executed": r["executed"],
        })
        for entry in (r["agent_contributions"] or []):
            if entry.get("type") == "market_snapshot":
                for feature, value in ((entry.get("data") or {}).get("features") or {}).items():
                    feature_records.append({
                        "feature": feature, "value": value,
                        "forward_label": forward_label, "day": r["day"],
                    })
        for agent in (r["agent_contributions"] or []):
            for signal, contribution in (agent.get("feature_contributions") or {}).items():
                if not isinstance(contribution, (int, float)):
                    continue
                signal_records.append({
                    "signal": signal, "contribution": contribution,
                    "forward_label": forward_label, "day": r["day"],
                    "regime": r["market_regime"],
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
        # Faz 459: negatif becerinin ne kadarı Council'in kendi katkısı,
        # ne kadarı kısa vadeli dönüş etkisine karşı çalışmaktan geliyor.
        "reversal_conditioning": compute_conditional_direction_value(records),
        # Faz 459'un ikinci, bağımsız bulgusu: icra kapıları sinyalin en
        # ters örneklerini seçip geçiriyor mu.
        "execution_selection_effect": compute_execution_selection_effect(records),
        # Faz 460: hangi HAM SİNYAL ters, hangisi doğru, hangisi aslında
        # rejim etiketinin kopyası.
        "signal_directional_value": compute_signal_directional_value(signal_records),
        # Faz 462: hiç ölçülmemiş bağlam özelliklerinin yön değeri.
        "feature_directional_value": compute_feature_directional_value(feature_records),
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
