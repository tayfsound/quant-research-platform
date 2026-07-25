"""
Uygulama Dependency Injection Konteyneri.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings, get_settings
from database.engine import async_session_factory
from events.message_bus import InMemoryMessageBus, get_message_bus


class AppContainer:
    """Merkezi IoC konteyneri."""

    def __init__(self) -> None:
        self._settings: Settings | None = None
        self._message_bus: InMemoryMessageBus | None = None

    @property
    def settings(self) -> Settings:
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    @property
    def message_bus(self) -> InMemoryMessageBus:
        if self._message_bus is None:
            self._message_bus = get_message_bus()
        return self._message_bus

    def session(self) -> AsyncSession:
        """Yeni bir async session döndürür."""
        return async_session_factory()


container = AppContainer()
