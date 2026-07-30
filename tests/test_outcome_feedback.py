from unittest.mock import patch
from services.outcome_tracker import OutcomeTracker

def test_build_training_dataset():
    tracker = OutcomeTracker()
    with patch("services.outcome_tracker.TrainingDatasetBuilder") as MockBuilder:
        MockBuilder.return_value.build.return_value = {"samples": 10, "path": "test.jsonl"}
        result = tracker.build_training_dataset("test.jsonl")
        assert result["samples"] == 10
