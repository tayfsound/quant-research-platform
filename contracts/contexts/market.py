"""MarketContext – piyasa verileri (heterojen)."""
from typing import Any

from pydantic import BaseModel, Field


class MarketContext(BaseModel):
    symbol: str = ""
    timeframe: str = ""
    features: dict[str, Any] = Field(default_factory=dict)     # sayısal veya kategorik
    raw_snapshot: dict[str, Any] = Field(default_factory=dict)  # ham/kategorik veri
    # Kullanıcı bulgusu: 15m backtest'lerde tekrar tekrar sıfır işlem
    # çıkıyordu. Kök neden: backtest/real_historical_backtest.py sadece
    # technical/quant/pattern (+macro) sinyali kuruyor — onchain/sentiment/
    # order_flow/relative_strength ajanları HİÇ gerçek veri almadan
    # (contract varsayılanlarıyla) çalışıyor, hepsi her cycle'da WAIT
    # diyordu. Sorun "WAIT demeleri" değildi (bu, veri yoksa dürüst/doğru
    # davranış) — sorun WAIT derken bile data_quality/evidence_strength
    # gibi alanların "gerçek veri var" seviyesinde (0.6-0.9) kalması,
    # yani effective_influence'ın yüksek çıkıp BeliefEngine.synthesize'daki
    # total_weight'i (paydayı) seyreltmesiydi — gerçekten yönlü oy veren
    # 4 ajanın (technical/pattern/quant/macro) sinyali, hiç konuşmamış 6
    # ajanın "kör WAIT"ı yüzünden confidence'ı reduce_threshold'a hiç
    # ulaştırmıyordu. Bu alan, hangi domain'lerin bu cycle'da GERÇEK veri
    # kaynağı olmadığını CouncilStage'e bildirir — o domain'ler hiç
    # çağrılmaz (deliberate() zaten ctx=None'ı atlıyor), kör bir WAIT
    # üretip payda şişirmez.
    data_unavailable_domains: list[str] = Field(default_factory=list)
