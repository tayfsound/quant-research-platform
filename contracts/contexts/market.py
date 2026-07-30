"""MarketContext – piyasa verileri (heterojen)."""
from typing import Any

from pydantic import BaseModel, Field


class MarketContext(BaseModel):
    symbol: str = ""
    timeframe: str = ""
    features: dict[str, Any] = Field(default_factory=dict)     # sayısal veya kategorik
    raw_snapshot: dict[str, Any] = Field(default_factory=dict)  # ham/kategorik veri
