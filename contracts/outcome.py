"""Outcome Feedback Architecture — DecisionEvaluation'a decision_score eklendi.

Faz 362-devam — kullanıcı kararı (2026-08-24): FailureType ve
OpportunityCost bağımlılığı kaldırıldı — ikisi de SADECE artık silinmiş
services/outcome_evaluator.py/services/opportunity_cost.py tarafından
kullanılıyordu (hiçbir zaman gerçek CognitiveEngine.run() akışına
bağlanmamış bir RL-tarzı ödül/skorlama tasarımının kalıntısı, bkz.
AI_MEMORY_SYSTEM/BACKLOG.md). TradeOutcome/DecisionEvaluation'ın
KENDİSİ kasıtlı olarak KORUNDU — hâlâ birden fazla regresyon testinin
(ör. tests/test_e2e_scenarios.py, tests/test_learning_loop.py) "bu
alan set edilse bile öğrenme döngüsü tetiklenmiyor" güvencesini
kanıtlamak için gerçekten kullandığı bir tip."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class TradeOutcome(BaseModel):
    trade_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.now)
    decision: str = ""
    confidence_at_decision: float = 0.0
    pnl: float = 0.0
    win: bool = False
    decision_correct: bool = False
    holding_time_seconds: int = 0
    max_adverse_excursion: float = 0.0
    max_favorable_excursion: float = 0.0
    exit_reason: str = ""

class DecisionEvaluation(BaseModel):
    original_confidence: float
    outcome: TradeOutcome
    confidence_error: float = 0.0
    decision_score: float = 0.0
    was_prediction_correct: bool = False
    learning_signal: str = ""
