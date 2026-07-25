"""Outcome Feedback Architecture — DecisionEvaluation'a decision_score eklendi."""
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4
from pydantic import BaseModel, Field
from contracts.opportunity import OpportunityCost

class FailureType(StrEnum):
    FALSE_REVERSAL = "false_reversal"
    TREND_CONTINUATION = "trend_continuation"
    VOLATILITY_EXPANSION = "volatility_expansion"
    LIQUIDITY_TRAP = "liquidity_trap"
    NEWS_IMPACT = "news_impact"
    MODEL_MISCONFIDENCE = "model_misconfidence"
    NONE = "none"

class TradeOutcome(BaseModel):
    trade_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.now)
    decision: str = ""
    confidence_at_decision: float = 0.0
    pnl: float = 0.0
    win: bool = False
    decision_correct: bool = False
    failure_type: FailureType = FailureType.NONE
    holding_time_seconds: int = 0
    max_adverse_excursion: float = 0.0
    max_favorable_excursion: float = 0.0
    exit_reason: str = ""
    opportunity_cost: OpportunityCost | None = None

class DecisionEvaluation(BaseModel):
    original_confidence: float
    outcome: TradeOutcome
    confidence_error: float = 0.0
    decision_score: float = 0.0
    was_prediction_correct: bool = False
    learning_signal: str = ""
