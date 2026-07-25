"""Eğitim pipeline'ı."""
from datetime import datetime

from ml.registry.store import ModelRegistry, ModelRegistryEntry


class TrainingPipeline:
    def __init__(self, registry: ModelRegistry):
        self.registry = registry

    def run(self, model_type: str, hyperparams: dict, metrics: dict) -> ModelRegistryEntry:
        entry = ModelRegistryEntry(
            model_type=model_type,
            version=f"{datetime.now().strftime('%Y%m%d%H%M%S')}",
            hyperparameters=hyperparams,
            metrics=metrics,
            trained_at=datetime.now(),
        )
        self.registry.register(entry)
        return entry
