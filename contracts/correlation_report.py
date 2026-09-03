"""Korelasyon Stabilitesi periyodik anlık görüntüsü — Faz 407.
market_state_report.py ile AYNI desen: pahalı (korelasyon matrisi, N
sembol için O(N^2)) — Celery periyodik görevi (5dk, market_state_gatherer
ile AYNI cycle'da, ek API çağrısı olmadan) bunu bir kez hesaplayıp
kaydediyor."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class CorrelationReport(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.now)
    # describe_correlation_pairs()'in çıktısı: {"pairs": [{"pair", "correlation", "correlation_stability"}]}
    result: dict | None = None
