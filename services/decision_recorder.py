from pathlib import Path

"""Decision recorder — Phase 165 replay compatible."""

from contracts.decision_event import DecisionEvent
from database.connection import get_session
from database.repositories.decision_persistor import DecisionPersistor


class DecisionRecorder:
    def __init__(self, storage_path=None):
        self.storage_path = Path(storage_path) if storage_path else None
        if self.storage_path:
            self.storage_path.mkdir(parents=True, exist_ok=True)
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

        agent_opinions_data = [op.model_dump() for op in (opinions or [])]
        if debate_result is not None:
            # Explainability chain (Sprint 16): debate_result used to be
            # accepted here and silently discarded — "hangi debate?" had no
            # answer for any real persisted decision. Folded into
            # agent_opinions (same list that flows into agent_contributions
            # in the DB) tagged distinctly so it's filterable.
            agent_opinions_data.append({
                "_type": "debate_result",
                "data": (
                    debate_result.model_dump()
                    if hasattr(debate_result, "model_dump")
                    else debate_result
                ),
            })

        event = DecisionEvent(
            id=ctx.cycle_id,
            timestamp=ctx.timestamp,
            symbol=ctx.market.symbol,
            proposed_direction=direction,
            final_action=direction,
            final_size=getattr(ctx.decision, "final_size", 0.0),
            confidence=getattr(ctx.decision, "confidence", 0.0),
            agent_opinions=agent_opinions_data,
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
            # Explainability chain: without this, belief_snapshot_id was
            # always NULL in the decisions table — belief IS saved
            # separately (MemoryService.store_belief in RecordingStage) but
            # nothing linked the decision row back to it. "hangi belief?"
            # was unanswerable for any real decision.
            belief_snapshot_id=belief.id if belief is not None else None,
        )

        self.persistor.persist(event)

        if self.storage_path:
            log_file = self.storage_path / f"decision_{event.id}.json"
            log_file.write_text(event.model_dump_json(indent=2))

        return event

    def replay(self, decision_id: str):
        data = self.persistor.get_by_id(decision_id)

        if data is None:
            return None

        return DecisionEvent(
            id=data["id"],
            timestamp=data["timestamp"],
            symbol=data["symbol"],
            proposed_direction=data.get("direction"),
            final_action=data.get("direction"),
            final_size=data.get("size", 0.0),
            confidence=data.get("confidence", 0.0),
            weight_snapshot_id=data.get("weight_snapshot_id"),
            belief_snapshot_id=data.get("belief_snapshot_id"),
        )

    def list_decisions(self, limit: int = 100):
        return self.persistor.list_recent(limit)
