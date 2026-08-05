"""RiskContext – hash doğrulamalı immutable risk limitleri."""
from enum import StrEnum
from hashlib import sha256

from pydantic import BaseModel, Field


class RiskAdjustmentSource(StrEnum):
    LLM = "llm"
    VOLATILITY_MODEL = "volatility_model"
    MANUAL = "manual"

class RiskReason(BaseModel):
    code: str
    message: str
    severity: str = "warning"  # "info", "warning", "critical"

class RiskLimitEntry(BaseModel):
    value: float
    hash: str = ""

    def verify(self, secret: str = "") -> bool:
        """Eğer hash boşsa (geliştirme modu) her zaman geçer."""
        if not self.hash:
            return True
        expected = sha256(f"{self.value}:{secret}".encode()).hexdigest()
        return expected == self.hash

class RiskAdjustment(BaseModel):
    source: RiskAdjustmentSource = RiskAdjustmentSource.MANUAL
    factor: float = 1.0

class RiskEvaluation(BaseModel):
    verdict: str = ""               # "approved" / "rejected"
    reasons: list[RiskReason] = Field(default_factory=list)

class RiskContext(BaseModel):
    limits: dict[str, RiskLimitEntry] = Field(default_factory=dict)
    current_exposure: float = 0.0
    current_drawdown: float = 0.0
    daily_pnl: float = 0.0
    adjustment: RiskAdjustment = Field(default_factory=RiskAdjustment)
    evaluation: RiskEvaluation = Field(default_factory=RiskEvaluation)
    # Faz 188: kullanıcının app_settings üzerinden kontrol ettiği operasyonel
    # sınırlar (bkz. services/risk_state.py) — "test" modunda RiskEngine tüm
    # kontrolleri atlar, "live" modunda hepsi devreye girer.
    trading_mode: str = "live"
    open_position_count: int = 0
    max_concurrent_positions: int | None = None
    capital_used_pct: float = 0.0
    max_capital_pct: float | None = None
