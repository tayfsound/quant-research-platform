"""Decision recorder — Phase 165 replay compatible."""

from database.repositories.decision_persistor import DecisionPersistor
from database.connection import get_session
from contracts.decision_event import DecisionEvent


class DecisionRecorder:
    def __init__(self, storage_path=None):
        self.session = get_session()
        self.persistor = DecisionPersistor(self.session)

    def record(
        self,
        ctx,
        opinions=None,
        belief=None,
        debate_result=None,
        weight_snapshot_id=None,
    ) -> DecisionEvent:

        direction = (
            getattr(ctx.decision, "proposed_direction", None)
            or getattr(ctx.decision, "final_action", "WAIT")
        )

        event = DecisionEvent(
            id=ctx.cycle_id,
            timestamp=ctx.timestamp,
            symbol=ctx.market.symbol,
            proposed_direction=direction,
            final_action=direction,
            final_size=getattr(ctx.decision, "final_size", 0.0),
            confidence=getattr(ctx.decision, "confidence", 0.0),

            agent_opinions=[
                op.model_dump()
                for op in (opinions or [])
            ],

            risk_evaluation=ctx.risk.evaluation.model_dump(),

            market_snapshot={
                "symbol": ctx.market.symbol,
                "timeframe": ctx.market.timeframe,
                "features": ctx.market.features,
                "raw_snapshot": ctx.market.raw_snapshot,
            },

            belief_state=(
                belief.model_dump()
                if belief and hasattr(belief, "model_dump")
                else None
            ),

            outcome=(
                ctx.outcome.model_dump()
                if ctx.outcome and hasattr(ctx.outcome, "model_dump")
                else None
            ),

            weight_snapshot_id=weight_snapshot_id,
        )

        return event
