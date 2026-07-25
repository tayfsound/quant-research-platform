"""Pozisyon ve risk takip motoru."""
from dataclasses import dataclass, field


@dataclass
class Position:
    symbol: str
    side: str
    quantity: float
    entry_price: float
    current_price: float = 0.0
    leverage: float = 1.0

    @property
    def notional(self) -> float:
        return self.quantity * self.current_price

    @property
    def unrealized_pnl(self) -> float:
        if self.side == "long":
            return self.quantity * (self.current_price - self.entry_price)
        return self.quantity * (self.entry_price - self.current_price)

@dataclass
class ExposureTracker:
    positions: dict[str, Position] = field(default_factory=dict)
    initial_balance: float = 100_000.0
    current_balance: float = 100_000.0
    peak_balance: float = 100_000.0
    daily_pnl: float = 0.0
    daily_loss: float = 0.0

    def add_position(self, position: Position):
        self.positions[position.symbol] = position

    def remove_position(self, symbol: str):
        self.positions.pop(symbol, None)

    def update_price(self, symbol: str, price: float):
        if symbol in self.positions:
            self.positions[symbol].current_price = price

    @property
    def total_exposure(self) -> float:
        return sum(p.notional for p in self.positions.values())

    @property
    def current_drawdown(self) -> float:
        if self.peak_balance == 0:
            return 0.0
        return (self.peak_balance - self.current_balance) / self.peak_balance

    def update_balance(self, new_balance: float):
        self.current_balance = new_balance
        if new_balance > self.peak_balance:
            self.peak_balance = new_balance
