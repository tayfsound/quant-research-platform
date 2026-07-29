from contracts.replay.replay_snapshot import ReplaySnapshot
from services.replay.decision_hash import create_decision_hash


def build_snapshot(event):

    data = {
        "symbol": event.symbol,
        "final_action": event.final_action,
        "final_size": event.final_size,
        "confidence": event.confidence,
        "market_snapshot": event.market_snapshot,
        "risk_evaluation": event.risk_evaluation,
        "belief_state": event.belief_state,
    }

    return ReplaySnapshot(
        snapshot_id=str(event.id),
        created_at=event.timestamp,
        decision_event_id=str(event.id),
        market_state=event.market_snapshot or {},
        risk_state=event.risk_evaluation or {},
        belief_state=event.belief_state or {},
        weight_snapshot_id=(
            str(event.weight_snapshot_id)
            if event.weight_snapshot_id
            else None
        ),
        decision_hash=create_decision_hash(data),
    )
