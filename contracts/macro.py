"""Macro Economics Domain Contracts."""
from datetime import datetime

from pydantic import BaseModel, Field


class MacroIndicator(BaseModel):
    """Tek bir makroekonomik gösterge."""
    name: str
    value: float
    previous_value: float | None = None
    expected_value: float | None = None
    timestamp: datetime = Field(default_factory=datetime.now)
    source: str = ""
    reliability: float = 0.8

class MacroContext(BaseModel):
    """MacroAgent için işlenmiş makro bağlam."""
    indicators: list[MacroIndicator] = Field(default_factory=list)
    inflation_trend: str = ""       # "rising", "falling", "stable"
    employment_trend: str = ""      # "improving", "weakening"
    liquidity_condition: str = ""   # "tight", "neutral", "loose"
    central_bank_bias: str = ""     # "hawkish", "neutral", "dovish"
    timestamp: datetime = Field(default_factory=datetime.now)
