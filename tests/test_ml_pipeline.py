"""ML pipeline testleri."""
from ml.models.classifier import DecisionClassifier
from ml.training.pipeline import TrainingPipeline
from ml.training.replay_memory import ReplayMemory


def test_pipeline_insufficient_data():
    pipe = TrainingPipeline()
    result = pipe.run(min_samples=100)
    assert result["status"] == "insufficient_data"

def test_classifier_train_predict():
    clf = DecisionClassifier()
    features = [
        {"f1": 1.0, "f2": 0.5},
        {"f1": 2.0, "f2": 1.5},
        {"f1": 3.0, "f2": 2.5},
    ]
    labels = [0, 1, 1]
    clf.train(features, labels)
    pred = clf.predict({"f1": 2.5, "f2": 2.0})
    assert "direction" in pred
    assert "confidence" in pred
    assert 0 <= pred["confidence"] <= 1

def test_pipeline_end_to_end():
    memory = ReplayMemory(capacity=100)
    for i in range(20):
        memory.add({
            "decision_id": f"dec_{i}",
            "timestamp": "2026-07-30T00:00:00",
            "raw": {
                "belief": {"direction": "LONG", "confidence": 0.8, "strength": 0.7},
                "outcome": {"pnl": 100 if i % 3 == 0 else -50}
            },
            "features": {"f1": float(i), "f2": float(i) * 0.5},
            "quality_score": 0.8,
            "label": 1 if i % 3 == 0 else 0
        })

    pipe = TrainingPipeline(memory=memory)
    result = pipe.run(min_samples=10)
    assert result["status"] == "trained"
    assert result["samples"] >= 10
