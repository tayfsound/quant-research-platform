"""Technical Analysis Domain Contracts."""
from datetime import datetime
from pydantic import BaseModel, Field

class TechnicalContext(BaseModel):
    """TechnicalAgent için yapısal teknik analiz bağlamı."""
    trend: str = "neutral"              # "bullish", "bearish", "neutral"
    momentum: str = "neutral"           # "strengthening", "weakening", "neutral"
    market_structure: str = "neutral"   # "higher_highs", "lower_lows", "ranging"
    volume_confirmation: bool = False   # Hacim trendi destekliyor mu?
    rsi_value: float = 50.0
    ema_alignment: str = "neutral"      # "bullish_aligned", "bearish_aligned", "mixed"
    volatility_regime: str = "normal"   # "low", "normal", "high"
    key_levels: list[float] = Field(default_factory=list)  # Kritik destek/direnç seviyeleri
    timestamp: datetime = Field(default_factory=datetime.now)
