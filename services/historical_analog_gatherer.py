"""Historical Analog Engine'in girdisini GERÇEK kapanmış kararlardan
toplayan tek kaynak — FIL Faz D. analytics/historical_analog_engine.py
saf (pure) kalıyor, gerçek veriye dokunan kod burada. services/agent_
combination_reliability_gatherer.py ile AYNI desen (pump_fade_v1 hariç —
council oylaması yok, mekanik strateji, anlaşma/rejim kavramı anlamsız),
sadece market_regime ve direction'ı da kayda ekliyor."""
from analytics.agent_combination_reliability import agreeing_domains_for_decision
from analytics.historical_analog_engine import compute_historical_analogs
from services.pump_fade_strategy import EXPERIMENT_BUCKET as PUMP_FADE_EXPERIMENT_BUCKET

MAX_DECISIONS = 2000


def gather_historical_analogs() -> dict:
    from database.repositories.decision_persistor import DecisionPersistor
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        closed_trades = DecisionPersistor(session).list_closed_trades(
            limit=MAX_DECISIONS, exclude_experiment_bucket=PUMP_FADE_EXPERIMENT_BUCKET
        )

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
        records.append({
            "agreeing_domains": agreeing,
            "market_regime": market_regime,
            "direction": final_direction,
            "win": pnl > 0,
            "closed_at": t.get("closed_at"),
        })

    result = compute_historical_analogs(records)
    result["n_trades"] = len(records)
    return result
