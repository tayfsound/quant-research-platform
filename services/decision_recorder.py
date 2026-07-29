"""Decision recorder — Phase 170: DB persistence, backward compatible API."""

from database.repositories.decision_persistor import DecisionPersistor
from database.connection import get_session
from contracts.decision_event import DecisionEvent


class DecisionRecorder:
    def __init__(self, storage_path=None):
        self.session = get_session()
        self.persistor = DecisionPersistor(self.session)

    def record(self, ctx, opinions=None, belief=None, debate_result=None, weight_snapshot_id=None) -> DecisionEvent:
        direction = getattr(ctx.decision, 'proposed_direction', None) or getattr(ctx.decision, 'final_action', 'WAIT')
        event = DecisionEvent(
            id=ctx.cycle_id,
            timestamp=ctx.timestamp,
            symbol=ctx.market.symbol,
            proposed_direction=direction,
            final_action=direction,
            final_size=getattr(ctx.decision, 'final_size', 0.0),
            confidence=getattr(ctx.decision, 'confidence', 0.0),
            agent_opinions=[op.model_dump() for op in (opinions or [])],
            weight_snapshot_id=weight_snapshot_id,
        )
        # persist CognitiveEngine._persist_and_learn içinde yapılır (çift insert önlendi)
        return event
