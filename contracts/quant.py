"""Quant Domain Contracts — istatistiksel/kantitatif sinyaller."""
from datetime import datetime

from pydantic import BaseModel, Field


class QuantContext(BaseModel):
    """QuantAgent için istatistiksel bağlam."""
    zscore: float = 0.0                    # Fiyatın rolling ortalamadan sapması (std cinsinden)
    realized_vol_percentile: float = 50.0  # Mevcut gerçekleşen volatilitenin tarihsel dağılımdaki yüzdesi (0-100)
    autocorrelation: float = 0.0           # -1..1, lag-1 getiri otokorelasyonu (momentum/mean-reversion ayrımı)
    hurst_exponent: float = 0.5            # <0.5 mean-reverting, ~0.5 random walk, >0.5 trending
    timestamp: datetime = Field(default_factory=datetime.now)
