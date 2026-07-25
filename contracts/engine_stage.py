"""EngineStage protokolü – tüm engine'ler aynı arayüzü uygular."""
from abc import abstractmethod
from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from contracts.context import CognitiveCycleContext

class EngineStage(Protocol):
    @abstractmethod
    def execute(self, ctx: "CognitiveCycleContext") -> "CognitiveCycleContext":
        ...
