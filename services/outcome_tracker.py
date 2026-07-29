from pathlib import Path

from contracts.outcome import TradeOutcome
from services.training_dataset_builder import TrainingDatasetBuilder
from database.connection import get_session
from database.repositories.decision_persistor import DecisionPersistor


class OutcomeTracker:
    def __init__(self, storage_path="decision_logs"):
        self.storage_path = Path(storage_path)

    def attach_outcome(self, decision_id: str, outcome: TradeOutcome):
        session = get_session()

        try:
            persistor = DecisionPersistor(session)
            data = persistor.get_by_id(decision_id)

            if not data:
                return None

            persistor.update_outcome(
                decision_id=decision_id,
                pnl=outcome.pnl,
                status="completed",
                outcome=outcome.model_dump(mode="json"),
            )

            from contracts.decision_event import DecisionEvent
            from uuid import UUID

            return DecisionEvent(
                id=UUID(decision_id),
                timestamp=data["timestamp"],
                symbol=data["symbol"],
                proposed_direction=data["direction"],
                final_action=data["direction"],
                final_size=data["size"] or 0.0,
                confidence=data["confidence"] or 0.0,
                agent_opinions=[],
                market_snapshot={},
                outcome=outcome.model_dump(mode="json"),
            )

        finally:
            session.close()

    def build_training_dataset(self, output_path="training_data.jsonl"):
        return TrainingDatasetBuilder().build(output_path)
