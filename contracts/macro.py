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
    # Faz 267 — kullanıcı bulgusu: "devletler borçlarını dört yıllık
    # dönemlerle öder, bu döngü tamamlanınca piyasaya likidite girer."
    # liquidity_condition (M2 büyümesi) bunu YAKALAMIYOR — M2 aylık,
    # yavaş değişen bir ölçü; Hazine'nin nakit hesabını (TGA) doldurup
    # boşaltması ve Fed'in ters repo tesisi haftalar içinde çok daha
    # büyük, çok daha hızlı likidite dalgalanmaları yaratıyor (borç
    # tavanı sonrası TGA yeniden dolarken likidite hızla çekilir, TGA
    # boşalırken piyasaya geri döner). Gerçek, tanınmış bir formül
    # (bkz. market_data/macro/fred_provider.py::fetch_net_liquidity_trend):
    # Net Likidite = Fed Bilançosu (WALCL) - Hazine Nakit Hesabı (WTREGEN)
    # - Ters Repo (RRPONTSYD).
    net_liquidity_trend: str = ""   # "expanding", "contracting", "stable"
    timestamp: datetime = Field(default_factory=datetime.now)
