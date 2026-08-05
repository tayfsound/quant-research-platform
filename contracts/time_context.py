"""Time/Seasonality Domain Contracts — zamansal/seansal bağlam."""
from datetime import datetime

from pydantic import BaseModel, Field


class TimeContext(BaseModel):
    """TimeAgent için zamansal bağlam. Not: zaman kendi başına yön tahmin
    etmez — bu ajan kanıtlanmamış "Pazartesi etkisi" gibi sinyaller
    uydurmuyor, sadece likidite/volatilite riskini (funding saati,
    hafta sonu) işaretleyip WAIT-ağırlıklı, dürüst bir görüş üretiyor."""
    session: str = "unknown"           # "asia", "europe", "us", "overlap"
    day_of_week: str = "unknown"
    hours_to_funding: float = 4.0      # Perpetual funding 8 saatte bir (00/08/16 UTC)
    is_weekend: bool = False
    timestamp: datetime = Field(default_factory=datetime.now)
