"""Eğitim pipeline'ı."""
from datetime import datetime

from ml.registry.store import ModelRegistry, ModelRegistryEntry
from ml.training.evaluation import ModelEvaluator
from ml.training.feature_extractor import TrainingFeatureExtractor


class TrainingPipeline:
    def __init__(self, registry: ModelRegistry):
        self.registry = registry
        self.extractor = TrainingFeatureExtractor()
        self.evaluator = ModelEvaluator()

    def run(self, model_type: str, predictions: list[dict], hyperparams: dict = None) -> ModelRegistryEntry:
        # Değerlendirme yap
        eval_result = self.evaluator.evaluate_predictions(predictions)

        entry = ModelRegistryEntry(
            model_type=model_type,
            version=f"{datetime.now().strftime('%Y%m%d%H%M%S')}",
            hyperparameters=hyperparams or {},
            metrics=eval_result.model_dump(),
            trained_at=datetime.now(),
        )
        self.registry.register(entry)
        return entry
