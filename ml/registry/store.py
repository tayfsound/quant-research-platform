"""Model kayıt ve versiyonlama sistemi."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel


class ModelRegistryEntry(BaseModel):
    id: UUID = uuid4()
    model_type: str
    version: str
    hyperparameters: dict = {}
    metrics: dict = {}
    checkpoint_path: str | None = None
    trained_at: datetime | None = None
    is_production: bool = False

class ModelRegistry:
    def __init__(self):
        self._models: dict[str, list[ModelRegistryEntry]] = {}

    def register(self, entry: ModelRegistryEntry):
        self._models.setdefault(entry.model_type, []).append(entry)

    def get_latest(self, model_type: str) -> ModelRegistryEntry | None:
        entries = self._models.get(model_type, [])
        return entries[-1] if entries else None

    def promote_to_production(self, model_type: str, version: str):
        for e in self._models.get(model_type, []):
            e.is_production = (e.version == version)
