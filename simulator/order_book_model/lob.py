"""Limit Order Book simülasyon modeli."""
from sortedcontainers import SortedDict


class SimulatedOrderBook:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.bids = SortedDict(lambda x: -x)  # En yüksek fiyat önce
        self.asks = SortedDict()              # En düşük fiyat önce

    def update(self, bid: float, ask: float, bid_size: float = 1.0, ask_size: float = 1.0):
        self.bids[bid] = bid_size
        self.asks[ask] = ask_size

    def market_order(self, side: str, quantity: float) -> tuple[float, float]:
        """Emri gerçekleştirir ve ortalama fiyat + slippage döner."""
        if side == "buy":
            levels = self.asks
        else:
            levels = self.bids

        filled = 0.0
        cost = 0.0
        for price, size in list(levels.items()):
            take = min(size, quantity - filled)
            cost += take * price
            filled += take
            levels[price] -= take
            if levels[price] <= 0:
                del levels[price]
            if filled >= quantity:
                break

        avg_price = cost / filled if filled > 0 else 0.0
        mid = (list(self.bids.keys())[0] + list(self.asks.keys())[0]) / 2 if self.bids and self.asks else 0.0
        slippage = abs(avg_price - mid) / mid if mid > 0 else 0.0
        return avg_price, slippage
