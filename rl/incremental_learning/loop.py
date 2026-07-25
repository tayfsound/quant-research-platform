"""Sürekli öğrenme döngüsü."""
from dataclasses import dataclass, field
from uuid import UUID, uuid4


@dataclass
class TradeOutcome:
    trade_id: UUID = field(default_factory=uuid4)
    symbol: str = "BTCUSDT"
    direction: int = 0
    entry_price: float = 0.0
    exit_price: float = 0.0
    pnl: float = 0.0
    features: dict[str, float] = field(default_factory=dict)
    agent_votes: dict[UUID, int] = field(default_factory=dict)

class IncrementalLearner:
    def __init__(self):
        self._history: list[TradeOutcome] = []

    def record(self, outcome: TradeOutcome):
        self._history.append(outcome)

    def analyze(self) -> dict:
        if not self._history:
            return {}
        wins = [t for t in self._history if t.pnl > 0]
        losses = [t for t in self._history if t.pnl <= 0]
        return {
            "win_rate": len(wins) / len(self._history),
            "avg_win": sum(t.pnl for t in wins) / len(wins) if wins else 0.0,
            "avg_loss": sum(t.pnl for t in losses) / len(losses) if losses else 0.0,
            "profit_factor": abs(sum(t.pnl for t in wins)) / abs(sum(t.pnl for t in losses)) if losses else float("inf"),
        }
