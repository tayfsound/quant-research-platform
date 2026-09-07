"""Direction Kalibrasyonu (Faz 446, 2026-09-07) — GPT'nin 6 numaralı
önceliği: mevcut Brier/ECE HER YERDE trade-kârlılığı (`pnl>0`) tabanlı
`was_correct`i ölçüyor (bkz. `services/direction_prediction_v2_gatherer.py`,
`services/confidence_calibration.py`) — bu modül SIFIRDAN bir hesap
makinesi YAZMIYOR, `analytics/direction_prediction_v2.py::compute_brier_
score()` ve `analytics/calibration_uncertainty.py::compute_expected_
calibration_error()` zaten tamamen JENERİK (`[(tahmin edilen olasılık,
doğru mu), ...]`) — sadece DOĞRU (Faz 441'in forward_direction etiketine
dayalı) girdiyi veriyor.

Mevcut trade-outcome tabanlı çağrılara (direction_prediction_v2_gatherer.py,
confidence_calibration.py) HİÇ DOKUNULMUYOR — bu YENİ, EK bir ölçüm.
Karşılaştırmayı doğrudan anlamlı kılmak için AYNI karar kümesinden hem
direction hem trade-outcome Brier/ECE'sini birlikte hesaplıyor (elma-elma
karşılaştırması, iki ayrı sorgu/iki ayrı pencere değil).

Karar seviyesindeki `confidence` alanı kullanılıyor (AgentMemory'nin
ajan-seviyesi confidence'ı DEĞİL) — GPT'nin "trade confidence"tan AYRI
"direction confidence" ayrımının en basit, mevcut-veriyle-mümkün hâli:
AI'nin NİHAİ kararına ne kadar güvendiği, gerçek yön isabetiyle ne kadar
örtüşüyor. NEUTRAL forward_label'lı kayıtlar dışlanır (fail-closed —
"yönü doğru mu bildi" sorusu, fiyat pratikte hareket etmediğinde
anlamsızdır)."""
from datetime import timedelta

from analytics.calibration_uncertainty import compute_expected_calibration_error
from analytics.direction_prediction_v2 import compute_brier_score
from analytics.evaluation_cohort import describe_evaluation_window
from analytics.forward_direction import DEFAULT_THRESHOLD_PCT, label_forward_direction
from services.pump_fade_strategy import EXPERIMENT_BUCKET as PUMP_FADE_EXPERIMENT_BUCKET

MAX_DECISIONS = 8000
DEFAULT_HORIZON = timedelta(hours=1)
DEFAULT_TOLERANCE_MINUTES = 5.0


def gather_direction_calibration(
    horizon: timedelta = DEFAULT_HORIZON,
    tolerance_minutes: float = DEFAULT_TOLERANCE_MINUTES,
    threshold_pct: float = DEFAULT_THRESHOLD_PCT,
) -> dict:
    from sqlalchemy import text

    from database.session_factory import SessionFactory

    tolerance = timedelta(minutes=tolerance_minutes)
    with SessionFactory.get_session() as session:
        rows = session.execute(
            text("""
                SELECT d.confidence, d.direction, d.entry_price, d.pnl, d.closed_at,
                       ms.close AS price_at_horizon
                FROM decisions d
                JOIN LATERAL (
                    SELECT close FROM market_snapshots ms2
                    WHERE ms2.exchange = 'binance' AND ms2.symbol = d.symbol AND ms2.resolution = '1m'
                      AND ms2.time BETWEEN d.timestamp + :horizon - :tolerance
                                        AND d.timestamp + :horizon + :tolerance
                    ORDER BY abs(extract(epoch FROM (ms2.time - (d.timestamp + :horizon))))
                    LIMIT 1
                ) ms ON true
                WHERE d.status = 'closed' AND d.excluded_from_stats = false
                  AND d.direction IN ('LONG', 'SHORT')
                  AND d.entry_price IS NOT NULL AND d.entry_price != 0
                  AND d.confidence IS NOT NULL
                  AND (d.experiment_bucket IS NULL OR d.experiment_bucket != :exclude_bucket)
                ORDER BY d.timestamp DESC
                LIMIT :limit
            """),
            {
                "horizon": horizon, "tolerance": tolerance,
                "exclude_bucket": PUMP_FADE_EXPERIMENT_BUCKET, "limit": MAX_DECISIONS,
            },
        ).mappings().all()

    direction_predictions: list[tuple[float, bool]] = []
    trade_outcome_predictions: list[tuple[float, bool]] = []
    for r in rows:
        confidence = r["confidence"]
        if r["pnl"] is not None:
            trade_outcome_predictions.append((confidence, r["pnl"] > 0))

        forward_label = label_forward_direction(r["entry_price"], r["price_at_horizon"], threshold_pct)
        if forward_label not in ("UP", "DOWN"):
            continue
        direction_correct = (
            (r["direction"] == "LONG" and forward_label == "UP")
            or (r["direction"] == "SHORT" and forward_label == "DOWN")
        )
        direction_predictions.append((confidence, direction_correct))

    return {
        "direction": {
            "brier": compute_brier_score(direction_predictions),
            "ece": compute_expected_calibration_error(direction_predictions),
            "n": len(direction_predictions),
        },
        "trade_outcome": {
            "brier": compute_brier_score(trade_outcome_predictions),
            "ece": compute_expected_calibration_error(trade_outcome_predictions),
            "n": len(trade_outcome_predictions),
        },
        "horizon_minutes": round(horizon.total_seconds() / 60, 1),
        "evaluation_window": describe_evaluation_window(
            [dict(r) for r in rows], limit=MAX_DECISIONS,
            exclude_experiment_buckets=[PUMP_FADE_EXPERIMENT_BUCKET],
        ),
    }
