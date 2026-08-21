"""Volatility Domain Contract — Faz 336. Deribit DVOL (kriptonun VIX'i) —
direction'dan bağımsız, ayrı bir risk/rejim ekseni."""
from datetime import datetime

from pydantic import BaseModel, Field


class VolatilityContext(BaseModel):
    """VolatilityAgent için işlenmiş implied volatility bağlamı."""
    dvol_level: float | None = None   # BTC DVOL, yıllıklandırılmış % (ör. 45.0)
    dvol_trend: str = ""              # "spiking", "falling", "stable"
    timestamp: datetime = Field(default_factory=datetime.now)
