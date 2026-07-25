"""
Olay (Event) şemaları.
"""
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from contracts.ml import Direction, ModelType
from contracts.risk import LimitType, RiskVerdictType
from contracts.simulation import FillReason, OrderSide, OrderType


class EventType(StrEnum):
    MARKET_SNAPSHOT = "market_snapshot"
    ORDER_BOOK_UPDATE = "order_book_update"
    FEATURE_VECTOR = "feature_vector"
    PREDICTION = "prediction"
    PROPOSED_DECISION = "proposed_decision"
    RISK_VERDICT = "risk_verdict"
    SIMULATED_FILL = "simulated_fill"
    LEARNING_UPDATE = "learning_update"
    EXPERIMENT_COMPLETED = "experiment_completed"
    RISK_LIMIT_VIOLATION = "risk_limit_violation"
    SYSTEM_ALERT = "system_alert"

class BaseEvent(BaseModel):
    event_id: UUID
    event_type: EventType
    timestamp: datetime
    version: str = "1.0"
    source: str

class MarketSnapshotEvent(BaseEvent):
    event_type: EventType = EventType.MARKET_SNAPSHOT
    symbol: str
    exchange: str
    resolution: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    quality_score: float = 1.0

class FeatureVectorEvent(BaseEvent):
    event_type: EventType = EventType.FEATURE_VECTOR
    symbol: str
    feature_set_version: str
    values: dict[str, float]

class PredictionEvent(BaseEvent):
    event_type: EventType = EventType.PREDICTION
    model_id: UUID
    model_type: ModelType
    model_version: str
    symbol: str
    direction: Direction
    confidence: float = Field(ge=0.0, le=1.0)
    raw_output: dict[str, Any] = Field(default_factory=dict)

class ProposedDecisionEvent(BaseEvent):
    event_type: EventType = EventType.PROPOSED_DECISION
    strategy_id: UUID
    symbol: str
    direction: Direction
    confidence: float
    size: float
    stop_loss: float | None = None
    take_profit: float | None = None
    rationale: str = ""

class RiskVerdictEvent(BaseEvent):
    event_type: EventType = EventType.RISK_VERDICT
    decision_id: UUID
    verdict: RiskVerdictType
    reason: str | None = None
    limit_triggered: LimitType | None = None
    rule_version: int

class LearningEventPayload(BaseEvent):
    event_type: EventType = EventType.LEARNING_UPDATE
    agent_id: UUID
    trajectory_id: UUID
    total_reward: float
    new_metrics: dict[str, Any] = Field(default_factory=dict)

class SimulatedFillEventPayload(BaseEvent):
    event_type: EventType = EventType.SIMULATED_FILL
    order_id: UUID
    strategy_id: UUID
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    fee: float
    slippage: float
    latency_ms: int
    order_type: OrderType
    leverage: float
    reason: FillReason
    liquidation: bool = False

class ExperimentCompletedEvent(BaseEvent):
    event_type: EventType = EventType.EXPERIMENT_COMPLETED
    experiment_id: UUID
    model_type: ModelType
    metrics: dict[str, Any]
    model_version: str | None = None

class RiskLimitViolationEvent(BaseEvent):
    event_type: EventType = EventType.RISK_LIMIT_VIOLATION
    limit_type: LimitType
    current_value: float
    limit_value: float
    scope: str
    severity: str = "warning"
