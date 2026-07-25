"""Deney takip sistemi."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel


class ExperimentRun(BaseModel):
    id: UUID = uuid4()
    name: str
    model_type: str
    hyperparameters: dict = {}
    metrics: dict = {}
    created_at: datetime = datetime.now()

class ExperimentTracker:
    def __init__(self):
        self._runs: list[ExperimentRun] = []

    def log(self, run: ExperimentRun):
        self._runs.append(run)

    def list(self) -> list[ExperimentRun]:
        return self._runs
