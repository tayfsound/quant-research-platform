"""Order book yönetimi."""
from contracts.exchange import OrderBookSnapshot


class OrderBookManager:
    def __init__(self):
        self._snapshots: dict[str, OrderBookSnapshot] = {}

    def apply(self, snapshot: OrderBookSnapshot):
        self._snapshots[snapshot.symbol] = snapshot

    def get(self, symbol: str) -> OrderBookSnapshot | None:
        return self._snapshots.get(symbol)
