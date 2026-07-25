"""
Analitik, Backtesting ve Raporlama portları ve şemaları.
"""
from abc import abstractmethod
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, Field


class BacktestType(StrEnum):
    HISTORICAL = "historical"
    WALK_FORWARD = "walk_forward"
    MONTE_CARLO = "monte_carlo"
    STRESS = "stress"

class RegimeLabel(StrEnum):
    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    LIQUIDITY_CRISIS = "liquidity_crisis"
    MANIPULATION = "manipulation"

class ReportFormat(StrEnum):
    PDF = "pdf"
    JSON = "json"
    CSV = "csv"
    XLSX = "xlsx"

class BacktestConfig(BaseModel):
    id: UUID | None = None
    name: str
    backtest_type: BacktestType
    strategy_id: UUID
    symbols: list[str]
    start_date: datetime
    end_date: datetime
    initial_capital: float = 100000.0
    parameters: dict[str, Any] = Field(default_factory=dict)

class BacktestMetrics(BaseModel):
    total_return: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown: float
    max_drawdown_duration_days: int
    win_rate: float
    profit_factor: float
    avg_trade_return: float
    num_trades: int
    volatility: float
    var_95: float
    cvar_95: float

class RegimeResult(BaseModel):
    symbol: str
    timestamp: datetime
    regime: RegimeLabel
    confidence: float = Field(ge=0.0, le=1.0)
    indicators: dict[str, float] = Field(default_factory=dict)

class ReportRequest(BaseModel):
    backtest_id: UUID | None = None
    strategy_id: UUID | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    format: ReportFormat = ReportFormat.PDF

class ReportResult(BaseModel):
    id: UUID
    format: ReportFormat
    file_path: str
    created_at: datetime

class ReportPort(Protocol):
    @abstractmethod
    async def compute_metrics(self, fills: list[Any]) -> BacktestMetrics: ...

    @abstractmethod
    async def generate_report(self, request: ReportRequest) -> ReportResult: ...

    @abstractmethod
    async def detect_regime(self, symbol: str, timestamp: datetime) -> RegimeResult: ...

    @abstractmethod
    async def compare_strategies(
        self, strategy_ids: list[UUID], start_date: datetime, end_date: datetime
    ) -> dict[str, BacktestMetrics]: ...
