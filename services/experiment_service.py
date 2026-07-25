"""Experiment Service — deney kayıt ve karşılaştırma."""
from uuid import UUID

from contracts.experiment import Experiment, ExperimentStatus


class ExperimentService:
    def __init__(self):
        self._experiments: dict[UUID, Experiment] = {}

    def register(self, experiment: Experiment) -> Experiment:
        self._experiments[experiment.id] = experiment
        return experiment

    def approve(self, experiment_id: UUID) -> Experiment | None:
        exp = self._experiments.get(experiment_id)
        if exp:
            exp.status = ExperimentStatus.APPROVED
        return exp

    def complete(self, experiment_id: UUID, metrics: dict, verdict: str) -> Experiment | None:
        exp = self._experiments.get(experiment_id)
        if exp:
            exp.status = ExperimentStatus.COMPLETED
            exp.metrics = metrics
            exp.verdict = verdict
        return exp

    def list_by_status(self, status: ExperimentStatus) -> list[Experiment]:
        return [e for e in self._experiments.values() if e.status == status]

    def compare(self, ids: list[UUID]) -> dict:
        experiments = [self._experiments[i] for i in ids if i in self._experiments]
        return {
            "experiments": [
                {"name": e.name, "verdict": e.verdict, "metrics": e.metrics}
                for e in experiments
            ]
        }
