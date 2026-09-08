"""Council vs Historical Analog Uzlaşım Raporunun girdisini GERÇEK
kapanmış kararlardan toplayan tek kaynak — Faz 452 (2026-09-08).
analytics/council_analog_agreement.py saf (pure) kalıyor, gerçek veriye
dokunan kod burada.

İki AYRI pencere: `cutoff`'tan ÖNCEKİ kararlardan (train) gate_eligible
analog hücreleri hesaplanıyor (historical_analog_gatherer.py İLE AYNI
agreeing_domains/reversing/volatility_regime/structure_phase/trade_type
çıkarımı, sadece zaman filtresi eklendi) — `cutoff`'tan SONRAKİ kararlar
(holdout) bu hesaplamaya HİÇ girmiyor, GERÇEKTEN tutulmuş/yeni veri."""
from datetime import timedelta

from analytics.agent_combination_reliability import agreeing_domains_for_decision
from analytics.council_analog_agreement import compute_council_vs_analog_agreement
from analytics.evaluation_cohort import describe_evaluation_window
from analytics.historical_analog_engine import compute_historical_analogs
from market_data.features.market_state_engine import market_state_reversing_for_decision
from services.historical_analog_gatherer import _market_snapshot_data
from services.pump_fade_strategy import EXPERIMENT_BUCKET as PUMP_FADE_EXPERIMENT_BUCKET
from services.strategy_regime_compatibility_gatherer import _trade_type

MAX_TRAIN_DECISIONS = 8000
DEFAULT_HOLDOUT_HOURS = 48


def _build_records(closed_trades: list[dict]) -> list[dict]:
    records = []
    for t in closed_trades:
        contributions = t.get("agent_contributions")
        final_direction = t.get("direction")
        market_regime = t.get("market_regime")
        pnl = t.get("pnl")
        if not contributions or not final_direction or not market_regime or pnl is None:
            continue
        agreeing = agreeing_domains_for_decision(contributions, final_direction)
        if agreeing is None:
            continue
        snapshot = _market_snapshot_data(contributions)
        records.append({
            "agreeing_domains": agreeing,
            "market_regime": market_regime,
            "direction": final_direction,
            "reversing": market_state_reversing_for_decision(contributions),
            "volatility_regime": (snapshot.get("features") or {}).get("volatility_regime"),
            "structure_phase": (snapshot.get("raw_snapshot") or {}).get("structure_phase"),
            "trade_type": _trade_type(t.get("entry_price"), t.get("stop_loss_price")),
            "win": pnl > 0,
            "closed_at": t.get("closed_at"),
        })
    return records


def gather_council_vs_analog_agreement(
    holdout_hours: float = DEFAULT_HOLDOUT_HOURS,
    max_train_decisions: int = MAX_TRAIN_DECISIONS,
) -> dict:
    from datetime import UTC, datetime

    from sqlalchemy import text

    from database.session_factory import SessionFactory

    cutoff = datetime.now(UTC) - timedelta(hours=holdout_hours)

    # list_closed_trades()'in tek bir limit'i, train(eski)/holdout(yeni)
    # ikisini AYNI ANDA doğru boyutlandıramaz (holdout penceresindeki
    # gerçek karar sayısı günlük hacme göre değişiyor) — closed_at
    # üstünden AYRI iki sorgu, ikisi de kendi doğru sınırında.
    with SessionFactory.get_session() as session:
        train_trades = session.execute(
            text("""
                SELECT * FROM decisions
                WHERE status = 'closed' AND excluded_from_stats = false
                  AND closed_at IS NOT NULL AND closed_at < :cutoff
                  AND (experiment_bucket IS NULL OR experiment_bucket != :exclude_bucket)
                ORDER BY closed_at DESC LIMIT :limit
            """),
            {"cutoff": cutoff, "exclude_bucket": PUMP_FADE_EXPERIMENT_BUCKET, "limit": max_train_decisions},
        ).mappings().all()
        holdout_trades = session.execute(
            text("""
                SELECT * FROM decisions
                WHERE status = 'closed' AND excluded_from_stats = false
                  AND closed_at IS NOT NULL AND closed_at >= :cutoff
                  AND (experiment_bucket IS NULL OR experiment_bucket != :exclude_bucket)
                ORDER BY closed_at DESC
            """),
            {"cutoff": cutoff, "exclude_bucket": PUMP_FADE_EXPERIMENT_BUCKET},
        ).mappings().all()

    train_trades = [dict(t) for t in train_trades]
    holdout_trades = [dict(t) for t in holdout_trades]

    train_records = _build_records(train_trades)
    holdout_records = _build_records(holdout_trades)

    analog_result = compute_historical_analogs(train_records)
    gate_eligible = [a for a in analog_result["analogs"] if a["gate_eligible"]]

    agreement = compute_council_vs_analog_agreement(gate_eligible, holdout_records)

    return {
        "cutoff": cutoff.isoformat(),
        "n_gate_eligible_analogs": len(gate_eligible),
        "gate_eligible_analogs": gate_eligible,
        "agreement": agreement,
        "train_window": describe_evaluation_window(
            train_trades, limit=max_train_decisions, exclude_experiment_buckets=[PUMP_FADE_EXPERIMENT_BUCKET],
        ),
        "holdout_window": describe_evaluation_window(
            holdout_trades, limit=None, exclude_experiment_buckets=[PUMP_FADE_EXPERIMENT_BUCKET],
        ),
    }
