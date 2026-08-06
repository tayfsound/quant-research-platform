"""CognitiveCycleContext — outcome alanı eklendi."""
from datetime import UTC, datetime
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
    # Faz 210: gerçek bulgu — naive datetime.now() (yerel makine saati,
    # bu ortamda CEST/UTC+2) hiç UTC'ye çevrilmeden opened_at/timestamp
    # kolonlarına yazılıyordu, ama services/position_closer.py closed_at'i
    # doğru şekilde datetime.now(UTC) ile üretiyordu — aynı satırda iki
    # farklı "saat" karışıyordu. Sonuç: gerçek ilk kapanan işlemlerde
    # closed_at, opened_at'ten ~2 saat ÖNCE görünüyordu (kullanıcı fark etti).
    # contracts/decision_event.py zaten datetime.now(UTC) kullanıyordu —
    # burası ona uyduruldu.
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    mode: ExecutionMode = ExecutionMode.EXPERIMENT

    market: MarketContext = Field(default_factory=MarketContext)
    cognition: CognitiveContext = Field(default_factory=CognitiveContext)
    risk: RiskContext = Field(default_factory=RiskContext)
    decision: Decision = Field(default_factory=Decision)

    outcome: TradeOutcome | None = None

DecisionContext = CognitiveCycleContext
