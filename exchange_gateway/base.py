"""
Tüm borsa adaptörleri için ortak base sınıf.
"""
from contracts.exchange import MarketDataPort


class BaseExchangeAdapter(MarketDataPort):
    """Ortak bağlantı yönetimi ve yeniden deneme mantığı."""
    def __init__(self, name: str) -> None:
        self.name = name
        self._connected = False

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected
