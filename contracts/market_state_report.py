"""Market State Cluster Engine periyodik anlık görüntüsü — Faz 401
(Market State Katmanı Faz 1). historical_analog_snapshots ile AYNI
desen: analytics/market_state_cluster_engine.py::compute_cluster_market_
state() pahalı (korelasyon matrisi + tüm sembollerin per-sembol market
state'i) — Celery periyodik görevi (5dk) bunu bir kez hesaplayıp
kaydediyor, canlı tüketiciler SADECE son satırı okuyor (ucuz DB
sorgusu)."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class MarketStateReport(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.now)
    # compute_cluster_market_state()'in çıktısı: {"by_symbol": {symbol: {...}}}
    result: dict | None = None
