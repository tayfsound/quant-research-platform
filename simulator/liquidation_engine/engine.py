"""Likidasyon motoru."""
from simulator.margin import MarginAccount


class LiquidationEngine:
    def __init__(self, maintenance_margin_rate: float = 0.005):
        self.maintenance_margin_rate = maintenance_margin_rate

    def check(self, account: MarginAccount, current_prices: dict[str, float]) -> list[str]:
        liquidated = []
        for symbol, pos in list(account.positions.items()):
            if symbol not in current_prices:
                continue
            current_price = current_prices[symbol]
            _ = (current_price - pos.entry_price) * pos.quantity if pos.side == "long" \
                  else (pos.entry_price - current_price) * pos.quantity
            equity = account.balance + sum(p for p in self._unrealized_pnl(account, current_prices).values())
            maintenance_margin = pos.margin_used * self.maintenance_margin_rate
            if equity < maintenance_margin:
                account.close_position(symbol, current_price)
                liquidated.append(symbol)
        return liquidated

    def _unrealized_pnl(self, account: MarginAccount, prices: dict[str, float]) -> dict[str, float]:
        result = {}
        for symbol, pos in account.positions.items():
            if symbol not in prices:
                continue
            price = prices[symbol]
            pnl = (price - pos.entry_price) * pos.quantity if pos.side == "long" \
                  else (pos.entry_price - price) * pos.quantity
            result[symbol] = pnl
        return result
