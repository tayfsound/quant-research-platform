"""Training Intelligence testleri."""
import json
from pathlib import Path

from services.training_intelligence import TrainingIntelligence


def test_generate_training_data():
    import tempfile
    from uuid import uuid4

    from contracts.decision_event import DecisionEvent

    with tempfile.TemporaryDirectory() as test_path_str:
        test_path = Path(test_path_str)
        intelligence = TrainingIntelligence(storage_path=test_path)

        event_id = uuid4()
        event = DecisionEvent(
            id=event_id,
            symbol="BTCUSDT",
            market_snapshot={"features": {"RSI": 45}},
            confidence=0.8,
            outcome={"pnl": 10.0, "win": True}
        )

        filename = test_path / f"decision_{event_id}.json"
        filename.write_text(event.model_dump_json())

        output_file = "test_training_dataset.jsonl"
        result = intelligence.generate_training_data(output_path=output_file)

        try:
            assert result["sample_count"] == 1
            assert Path(output_file).exists()
            with open(output_file) as f:
                data = json.loads(f.readline())
                assert data["label_pnl"] == 10.0
        finally:
            if Path(output_file).exists():
                Path(output_file).unlink()

    # Temizlik
    Path(output_file).unlink(missing_ok=True)
