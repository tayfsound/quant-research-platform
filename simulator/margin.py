"""Kaldıraç ve teminat yönetimi."""
from dataclasses import dataclass, field


@dataclass
class MarginAccount:
    balance: float = 100_000.0
    positions: dict[str, "Position"] = field(default_factory=dict)

    def open_position(self, symbol: str, side: str, quantity: float, price: float, leverage: float):
        notional = quantity * price
        margin = notional / leverage
        if margin > self.balance:
            raise ValueError("Yetersiz teminat")
        self.balance -= margin
        self.positions[symbol] = Position(
            symbol=symbol, side=side, quantity=quantity,
            entry_price=price, leverage=leverage, margin_used=margin
        )

    def close_position(self, symbol: str, exit_price: float):
        if symbol not in self.positions:
            return 0.0
        pos = self.positions.pop(symbol)
        pnl = (exit_price - pos.entry_price) * pos.quantity if pos.side == "long" \
              else (pos.entry_price - exit_price) * pos.quantity
        self.balance += pos.margin_used + pnl
        return pnl

@dataclass
class Position:
    symbol: str
    side: str
    quantity: float
    entry_price: float
    leverage: float
    margin_used: float
