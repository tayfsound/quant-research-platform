"""Pattern Recognition Domain Contracts — Wyckoff/Elliott/market structure."""
from datetime import datetime

from pydantic import BaseModel, Field


class PatternContext(BaseModel):
    """PatternAgent için yapısal/pattern bağlamı."""
    structure_phase: str = "neutral"       # "accumulation", "distribution", "markup", "markdown", "neutral" (Wyckoff)
    break_of_structure: str = "none"       # "bullish", "bearish", "none" (BOS)
    change_of_character: bool = False      # CHoCH — trend değişim uyarısı
    fair_value_gap: str = "none"           # "bullish", "bearish", "none" (FVG)
    swing_structure: str = "mixed"         # "higher_highs_higher_lows", "lower_highs_lower_lows", "mixed"
    liquidity_sweep: str = "none"          # "buy_side_swept", "sell_side_swept", "none"
    timestamp: datetime = Field(default_factory=datetime.now)
