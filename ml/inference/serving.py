"""Düşük gecikmeli tahmin servisi."""
from ml.registry.store import ModelRegistry


class InferenceService:
    def __init__(self, registry: ModelRegistry):
        self.registry = registry
        self._cache: dict[str, object] = {}

    def predict(self, model_type: str, features: list[float]) -> int:
        if model_type not in self._cache:
            entry = self.registry.get_latest(model_type)
            if entry is None:
                raise ValueError(f"Model {model_type} bulunamadı")
        # Basit stub: her zaman long
        return 1
