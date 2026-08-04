"""Backtest run contract — Sprint 6. Persisted results are Class 2 data:
never deleted, so a run's numbers can always be independently re-verified."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class BacktestRun(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.now)
    symbols: list[str] = Field(default_factory=list)
    git_sha: str = ""
    weight_snapshot_id: UUID | None = None
    fee: float = 0.0
    lookback: int = 0
    num_bars: int = 0
    total_pnl: float = 0.0
    per_symbol_pnl: dict[str, float] = Field(default_factory=dict)
    metrics: dict = Field(default_factory=dict)
    equity_curve: list[float] = Field(default_factory=list)
