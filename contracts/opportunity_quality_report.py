"""Opportunity Quality / Meta-Labeling haftalık anlık görüntüsü —
Cognitive Core 2.0 (Faz 569-593).

Kasıtlı olarak SADECE ölçüm/rapor — hiçbir pozisyon/risk kararını
otomatik değiştirmiyor."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class OpportunityQualityReport(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.now)
    # gather_opportunity_quality()'nin çıktısı
    result: dict | None = None
