"""Quant Domain Contracts — istatistiksel/kantitatif sinyaller."""
from datetime import datetime

from pydantic import BaseModel, Field


class QuantContext(BaseModel):
    """QuantAgent için istatistiksel bağlam."""
    zscore: float = 0.0                    # Fiyatın rolling ortalamadan sapması (std cinsinden)
    realized_vol_percentile: float = 50.0  # Mevcut gerçekleşen volatilitenin tarihsel dağılımdaki yüzdesi (0-100)
    autocorrelation: float = 0.0           # -1..1, lag-1 getiri otokorelasyonu (momentum/mean-reversion ayrımı)
    hurst_exponent: float = 0.5            # <0.5 mean-reverting, ~0.5 random walk, >0.5 trending
    # Faz 222: gerçek 200-periyotluk EMA'ya göre uzun-vade rejim — en az 220
    # bar (candle_lookback pagination ile artık mümkün) gerektirir, yoksa
    # "insufficient_data".
    long_term_trend_regime: str = "insufficient_data"
    # Faz 268-sonrası: gerçek olay (2026-08-12) — long_term_trend_regime
    # YAVAŞ/gecikmeli (200-EMA tabanlı), fiyat aktif olarak tersine
    # dönerken bile eski rejimi okumaya devam edebiliyor. Gerçek bir
    # istatistiksel iki-örneklem testi (market_data/features/signal_
    # engine.py::_regime_changepoint, Welch's t-test) son dönem
    # getirisinin, bu rejimin yönüne ters, anlamlı bir kayma gösterip
    # göstermediğini işaretliyor.
    regime_changepoint_detected: bool = False
    timestamp: datetime = Field(default_factory=datetime.now)
