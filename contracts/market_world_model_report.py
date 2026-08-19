"""Market World Model haftalık anlık görüntüsü — Cognitive Core 5.0-6.0
(Faz 901-940).

Kasıtlı olarak SADECE simülasyon/rapor — hiçbir pozisyon/risk kararını
otomatik değiştirmiyor."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class MarketWorldModelReport(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.now)
    # gather_market_world_model()'ın çıktısı
    result: dict | None = None
