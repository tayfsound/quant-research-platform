"""Outcome Tracker — düzeltilmiş JSON serialization ve ayrılmış feature."""
from pathlib import Path
import json
from datetime import datetime, UTC
from contracts.decision_event import DecisionEvent
from contracts.outcome import TradeOutcome, FailureType

class OutcomeTracker:
    def __init__(self, storage_path: str = "decision_logs"):
        self.storage_path = Path(storage_path)

    def attach_outcome(self, decision_id: str, outcome: TradeOutcome) -> DecisionEvent | None:
        filename = self.storage_path / f"decision_{decision_id}.json"
        if not filename.exists():
            return None

        event = DecisionEvent.model_validate_json(filename.read_text())
        event.outcome = outcome.model_dump(mode="json")
        filename.write_text(event.model_dump_json(indent=2, exclude_none=True))
        return event

    def build_training_dataset(self, output_path: str = "training_data.jsonl") -> int:
        count = 0
        with open(output_path, "w") as out:
            for filename in self.storage_path.glob("decision_*.json"):
                try:
                    event = DecisionEvent.model_validate_json(filename.read_text())
                    if event.outcome:
                        record = {
                            "features": event.market_snapshot.get("features", {}),
                            "raw_context": event.market_snapshot.get("raw_snapshot", {}),
                            "agent_opinions": event.agent_opinions,
                            "belief_strength": event.belief_state.get("strength", 0),
                            "decision": event.final_action,
                            "confidence": event.confidence,
                            "outcome": event.outcome,
                        }
                        out.write(json.dumps(record, default=str) + "\n")
                        count += 1
                except Exception:
                    pass
        return count
