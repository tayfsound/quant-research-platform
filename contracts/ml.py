"""
Makine Öğrenmesi portları ve şemaları.
"""
from abc import abstractmethod
from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, Field


class ModelType(StrEnum):
    XGBOOST = "xgboost"
    LIGHTGBM = "lightgbm"
    CATBOOST = "catboost"
    RANDOM_FOREST = "random_forest"
    LSTM = "lstm"
    GRU = "gru"
    TRANSFORMER = "transformer"
    TFT = "temporal_fusion_transformer"
    CNN = "cnn"
    AUTOENCODER = "autoencoder"
    ISOLATION_FOREST = "isolation_forest"
    BAYESIAN = "bayesian"
    HMM = "hmm"
    NLP_SENTIMENT = "nlp_sentiment"

class Direction(IntEnum):
    SHORT = -1
    NEUTRAL = 0
    LONG = 1

class TrainingStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class ModelMetadata(BaseModel):
    id: UUID
    model_type: ModelType
    version: str
    description: str = ""
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    checkpoint_path: str | None = None
    trained_at: datetime | None = None
    dataset_version: str | None = None
    feature_set_version: str | None = None
    is_production: bool = False

class PredictionRequest(BaseModel):
    model_id: UUID
    symbol: str
    feature_vector: dict[str, float]
    sequence: list[dict[str, float]] | None = None

class PredictionResult(BaseModel):
    model_id: UUID
    model_version: str
    symbol: str
    direction: Direction
    confidence: float = Field(ge=0.0, le=1.0)
    raw_output: dict[str, Any] = Field(default_factory=dict)
    explainability: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime

class TrainingJob(BaseModel):
    id: UUID
    model_type: ModelType
    symbol: str
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    dataset_version: str
    feature_set_version: str
    status: TrainingStatus = TrainingStatus.QUEUED
    created_at: datetime

class ExperimentRun(BaseModel):
    id: UUID
    name: str
    model_type: ModelType
    hyperparameters: dict[str, Any]
    metrics: dict[str, Any]
    dataset_version: str
    feature_set_version: str
    model_version: str | None = None
    created_at: datetime

class PredictionPort(Protocol):
    @abstractmethod
    async def predict(self, request: PredictionRequest) -> PredictionResult: ...

class TrainingPort(Protocol):
    @abstractmethod
    async def submit_job(self, job: TrainingJob) -> UUID: ...

    @abstractmethod
    async def get_job_status(self, job_id: UUID) -> TrainingStatus: ...

    @abstractmethod
    async def get_model(self, model_id: UUID) -> ModelMetadata: ...

    @abstractmethod
    async def list_models(self, model_type: ModelType | None = None) -> list[ModelMetadata]: ...

    @abstractmethod
    async def promote_to_production(self, model_id: UUID) -> None: ...
