"""TP/SL Confluence haftalık anlık görüntüsü — Faz 299-300.

Ölçüm/rapor katmanı — RiskTargetStage'in gerçek stop/target hesabı
services/tp_sl_confluence_gatherer.py'nin AYNI mantığını (analytics/
tp_sl_confluence.py) canlı kararlarda kullanır, bu rapor sadece
gözlem/geriye dönük izleme içindir."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class TpSlConfluenceReport(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.now)
    # gather_tp_sl_confluence()'ın çıktısı
    result: dict | None = None
