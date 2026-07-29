from services.replay.decision_hash import create_decision_hash


class ReplayVerifier:

    def verify(self, snapshot, event):

        data = {
            "symbol": event.symbol,
            "final_action": event.final_action,
            "final_size": event.final_size,
            "confidence": event.confidence,
            "market_snapshot": event.market_snapshot,
            "risk_evaluation": event.risk_evaluation,
            "belief_state": event.belief_state,
        }

        replay_hash = create_decision_hash(data)

        return {
            "verified": replay_hash == snapshot.decision_hash,
            "original_hash": snapshot.decision_hash,
            "replay_hash": replay_hash,
        }
