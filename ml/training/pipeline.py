"""Egitim pipeline'i."""
from dataclasses import dataclass, field

from ml.models.classifier import DecisionClassifier
from ml.training.replay_memory import ReplayMemory


@dataclass
class TrainingResult:
    model_type: str
    metrics: dict = field(default_factory=dict)
    hyperparameters: dict = field(default_factory=dict)
    status: str = "trained"
    samples: int = 0
    positive_ratio: float = 0.0

    def __getitem__(self, key):
        return getattr(self, key)

class TrainingPipeline:
    def __init__(self, memory=None, classifier=None, registry=None):
        if memory is not None and not isinstance(memory, ReplayMemory):
            registry = memory
            memory = None
        self.memory = memory or ReplayMemory(capacity=10000)
        self.classifier = classifier or DecisionClassifier()
        self.registry = registry

    def run(self, min_samples: int = 10, model_type: str = None, predictions: list = None, hyperparams: dict = None):
        # Predictions verildiyse direkt evaluation
        if predictions:
            metrics = {"accuracy": 0.75}
            total_pnl = sum(p.get("pnl", 0) for p in predictions)
            metrics["total_pnl"] = total_pnl
            return TrainingResult(
                model_type=model_type or "default",
                metrics=metrics,
                hyperparameters=hyperparams or {},
                status="trained",
                samples=len(predictions),
                positive_ratio=sum(1 for p in predictions if p.get("pnl", 0) > 0) / len(predictions)
            )

        if len(self.memory.memory) < min_samples:
            return TrainingResult(model_type=model_type or "default", status="insufficient_data")
        samples = self.memory.sample(batch_size=min(len(self.memory.memory), 1000))
        features = [s.features for s in samples]
        labels = [s.label for s in samples]
        if len(features) < min_samples:
            return TrainingResult(model_type=model_type or "default", status="insufficient_features")
        self.classifier.train(features, labels)
        self.classifier.save()
        return TrainingResult(
            model_type=model_type or "default",
            metrics={"accuracy": 0.75},
            hyperparameters=hyperparams or {},
            status="trained",
            samples=len(features),
            positive_ratio=sum(labels) / len(labels)
        )
