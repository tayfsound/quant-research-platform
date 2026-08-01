"""Experiment Registry repository."""
from sqlalchemy import Column, String, DateTime, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from database.base import Base
from contracts.experiment_registry import ExperimentRegistry


class ExperimentRegistryModel(Base):
    __tablename__ = "experiment_registry"
    id = Column(UUID(as_uuid=True), primary_key=True)
    timestamp = Column(DateTime, nullable=False)
    git_sha = Column(String(40), nullable=False)
    risk_limits_version = Column(Integer, nullable=False)
    feature_schema_id = Column(String(64), nullable=False)
    prompt_hash = Column(String(64), nullable=False)
    model_id = Column(String(64), nullable=False)
    decision_ids = Column(JSON, default=list)


class ExperimentRegistryRepository:
    def __init__(self, session):
        self.session = session

    def save(self, experiment: ExperimentRegistry) -> None:
        row = ExperimentRegistryModel(
            id=experiment.id,
            timestamp=experiment.timestamp,
            git_sha=experiment.git_sha,
            risk_limits_version=experiment.risk_limits_version,
            feature_schema_id=experiment.feature_schema_id,
            prompt_hash=experiment.prompt_hash,
            model_id=experiment.model_id,
            decision_ids=experiment.decision_ids,
        )
        self.session.add(row)
        self.session.commit()

    def get_by_git_sha(self, git_sha: str):
        return self.session.query(ExperimentRegistryModel).filter_by(git_sha=git_sha).all()
