"""Decision — ActionType, confidence, uncertainty, reason, reconsideration."""
from enum import StrEnum
from pydantic import BaseModel, Field

class ActionType(StrEnum):
    ENTER_LONG = "ENTER_LONG"
    ENTER_SHORT = "ENTER_SHORT"
    WAIT = "WAIT"
    EXIT = "EXIT"
    REDUCE = "REDUCE"
    RECONSIDER = "RECONSIDER"

class DecisionReason(StrEnum):
    NO_SIGNAL = "NO_SIGNAL"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    HIGH_RISK = "HIGH_RISK"
    STRONG_SIGNAL = "STRONG_SIGNAL"
    MEMORY_SUPPORTED = "MEMORY_SUPPORTED"

class Decision(BaseModel):
    proposed_direction: str = ""
    proposed_size: float = 0.0
    risk_adjusted_size: float = 0.0
    final_direction: str = ""
    final_size: float = 0.0
    action: ActionType = ActionType.WAIT
    reason: DecisionReason = DecisionReason.NO_SIGNAL
    confidence: float = 0.0
    uncertainty: float = 1.0
    reconsideration_count: int = 0
    take_profit: float | None = None
    stop_loss: float | None = None
