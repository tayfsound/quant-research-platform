"""Decision Replay portu."""
from abc import abstractmethod
from typing import Protocol
from uuid import UUID


class DecisionReplayPort(Protocol):
    @abstractmethod
    async def replay(self, trade_id: UUID) -> dict:
        """
        Aynı market snapshot, feature vector, risk limitleri ve prompt'u al,
        güncel modellerle kararı yeniden değerlendir.
        Dönüş: {"original_direction": ..., "new_direction": ..., "diff": ...}
        """
        ...
