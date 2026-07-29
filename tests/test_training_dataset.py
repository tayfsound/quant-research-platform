import json
from uuid import uuid4

from contracts.decision_event import DecisionEvent
from database.connection import get_session
from database.repositories.decision_persistor import DecisionPersistor
from services.training_dataset_builder import TrainingDatasetBuilder


def test_build_training_dataset(tmp_path):
    session = get_session()
    persistor = DecisionPersistor(session)

    event = DecisionEvent(
        id=uuid4(),
        symbol="BTCUSDT",
        proposed_direction="LONG",
        final_action="ENTER_LONG",
        final_size=1.0,
        confidence=0.9,
    )

    persistor.persist(event)
    persistor.update_outcome(
        str(event.id),
        pnl=100.0,
        status="completed",
        outcome={"pnl": 100.0, "win": True},
    )

    output = tmp_path / "training.jsonl"

    count = TrainingDatasetBuilder().build(str(output))

    assert count >= 1

    rows = output.read_text().splitlines()
    sample = json.loads(rows[-1])

    assert sample["symbol"] == "BTCUSDT"
    assert sample["label"] == 1
