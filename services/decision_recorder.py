"""Decision Recorder — deterministik kayıt, hash, latency, debate trace."""
import json
import time
import hashlib
from pathlib import Path
from contracts.decision_event import DecisionEvent
from contracts.context import CognitiveCycleContext
from contracts.belief import Belief
from contracts.agent import AgentOpinion
from contracts.agent import DebateResult


class DecisionRecorder:

    def __init__(self, storage_path: str = "decision_logs"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(exist_ok=True)


    def record(
        self,
        ctx: CognitiveCycleContext,
        opinions: list[AgentOpinion],
        belief: Belief | None = None,
        debate_result: DebateResult | None = None,
        weight_snapshot_id=None,
    ) -> DecisionEvent:

        start = time.perf_counter()

        feature_payload = json.dumps(
            {
                "features": ctx.market.features,
                "raw_snapshot": ctx.market.raw_snapshot,
            },
            sort_keys=True,
            default=str,
        )

        feature_hash = hashlib.sha256(
            feature_payload.encode()
        ).hexdigest()


        belief_hash = ""

        if belief:
            belief_payload = json.dumps(
                belief.model_dump(),
                sort_keys=True,
                default=str,
            )
            belief_hash = hashlib.sha256(
                belief_payload.encode()
            ).hexdigest()


        event = DecisionEvent(
            symbol=ctx.market.symbol,

            market_snapshot={
                "features": ctx.market.features,
                "raw_snapshot": ctx.market.raw_snapshot,
            },

            agent_opinions=[
                o.model_dump(mode="json")
                for o in opinions
            ],

            belief_state=(
                belief.model_dump(mode="json")
                if belief else {}
            ),

            risk_evaluation={
                "verdict": ctx.risk.evaluation.verdict,
                "reasons": ctx.risk.evaluation.reasons,
            },

            proposed_direction=ctx.decision.proposed_direction,

            final_action=(
                ctx.decision.action.value
                if ctx.decision.action
                else "WAIT"
            ),

            final_size=ctx.decision.final_size,

            confidence=ctx.decision.confidence,

            decision_latency_ms=round(
                (time.perf_counter() - start) * 1000,
                3,
            ),

            feature_hash=feature_hash,

            belief_hash=belief_hash,

            data_sources=[
                "market_context",
                "agent_council",
                "belief_engine",
            ],

            debate_trace=(
                debate_result.model_dump(mode="json")
                if hasattr(debate_result, "model_dump")
                else debate_result
                if debate_result
                else None
            ),

            weight_snapshot_id=weight_snapshot_id,
        )


        filename = self.storage_path / f"decision_{event.id}.json"

        filename.write_text(
            event.model_dump_json(
                indent=2,
                exclude_none=True,
            )
        )


        index_file = self.storage_path / "index.jsonl"

        with open(index_file, "a") as f:
            f.write(
                json.dumps({
                    "id": str(event.id),
                    "timestamp": event.timestamp.isoformat(),
                    "symbol": event.symbol,
                    "action": event.final_action,
                }) + "\n"
            )


        return event


    def replay(self, decision_id: str) -> DecisionEvent | None:

        filename = self.storage_path / f"decision_{decision_id}.json"

        if not filename.exists():
            return None

        return DecisionEvent.model_validate_json(
            filename.read_text()
        )


    def list_decisions(self, limit: int = 20) -> list[dict]:

        index_file = self.storage_path / "index.jsonl"

        if not index_file.exists():
            return []

        lines = index_file.read_text().strip().split("\n")

        return [
            json.loads(line)
            for line in lines[-limit:]
        ]
