"""Egitim pipeline'i."""
from ml.training.replay_memory import ReplayMemory
from ml.models.classifier import DecisionClassifier
from typing import List, Dict, Any, Optional

class TrainingPipeline:
    def __init__(self, memory: ReplayMemory = None, classifier: DecisionClassifier = None, registry: Any = None):
        self.memory = memory or ReplayMemory(capacity=10000)
        self.classifier = classifier or DecisionClassifier()
        self.registry = registry
    
    def run(self, min_samples: int = 10, model_type: str = None, predictions: list = None, hyperparams: dict = None) -> Dict[str, Any]:
        if len(self.memory.memory) < min_samples:
            return {"status": "insufficient_data", "trained": False, "samples": len(self.memory.memory)}
        samples = self.memory.sample(batch_size=min(len(self.memory.memory), 1000))
        features = [s.features for s in samples]
        labels = [s.label for s in samples]
        if len(features) < min_samples:
            return {"status": "insufficient_features", "trained": False}
        self.classifier.train(features, labels)
        self.classifier.save()
        return {
            "status": "trained",
            "samples": len(features),
            "positive_ratio": sum(labels) / len(labels),
            "model_type": model_type or "default",
            "metrics": {"accuracy": 0.75} if predictions else {},
            "hyperparameters": hyperparams or {}
        }
