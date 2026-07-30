"""CognitiveCycleContext — outcome alanı eklendi."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from contracts.contexts.cognitive import CognitiveContext
from contracts.contexts.decision import Decision
from contracts.contexts.market import MarketContext
from contracts.contexts.risk import RiskContext
from contracts.execution_mode import ExecutionMode
from contracts.outcome import TradeOutcome


class CognitiveCycleContext(BaseModel):
    cycle_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.now)
    mode: ExecutionMode = ExecutionMode.EXPERIMENT

    market: MarketContext = Field(default_factory=MarketContext)
    cognition: CognitiveContext = Field(default_factory=CognitiveContext)
    risk: RiskContext = Field(default_factory=RiskContext)
    decision: Decision = Field(default_factory=Decision)

    outcome: TradeOutcome | None = None

DecisionContext = CognitiveCycleContext
