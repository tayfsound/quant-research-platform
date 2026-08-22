from __future__ import annotations

"""Repository portları."""
from abc import abstractmethod
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from contracts.decision_audit import DecisionAuditRecord

if TYPE_CHECKING:
    from meta_optimizer.collector import ExperimentLog


class ExperimentLogRepository(Protocol):
    @abstractmethod
    def record(self, log: ExperimentLog) -> None: ...
    @abstractmethod
    def get_recent(self, n: int) -> list[ExperimentLog]: ...
    @abstractmethod
    def count(self) -> int: ...

class DecisionAuditRepository(Protocol):
    @abstractmethod
    async def insert(self, record: DecisionAuditRecord) -> None: ...
    @abstractmethod
    async def get_by_trade_id(self, trade_id: UUID) -> DecisionAuditRecord | None: ...
    @abstractmethod
    async def list_by_symbol(self, symbol: str, limit: int = 100) -> list[DecisionAuditRecord]: ...
