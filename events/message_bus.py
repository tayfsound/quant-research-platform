"""
Olay yolu (event bus) soyutlaması.
"""
import asyncio
from abc import abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

Handler = Callable[..., Awaitable[None]]


class MessageBusPort(Protocol):
    @abstractmethod
    async def publish(self, event_type: str, payload: dict[str, Any]) -> None: ...

    @abstractmethod
    async def subscribe(self, event_type: str, handler: Handler) -> None: ...


class InMemoryMessageBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = {}

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        handlers = self._handlers.get(event_type, [])
        if not handlers:
            return
        await asyncio.gather(*(handler(**payload) for handler in handlers))

    async def subscribe(self, event_type: str, handler: Handler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)


_bus: InMemoryMessageBus | None = None


def get_message_bus() -> InMemoryMessageBus:
    global _bus
    if _bus is None:
        _bus = InMemoryMessageBus()
    return _bus
