"""Collective Intelligence (Condorcet'in Jüri Teoremi) haftalık anlık
görüntüsü — Cognitive Core 10.0.

analytics/collective_intelligence.py::compute_expected_majority_
accuracy() gerçek zamanlı çalışır (GET /collective-intelligence/) ama
hiçbir geçmişi yoktu — bu tablo periyodik (haftalık) anlık görüntüleri
saklıyor, Self-Model/Causal Inference ile AYNI desen.

Kasıtlı olarak SADECE değerlendirme/rapor — hiçbir ajan ağırlığını
otomatik değiştirmiyor."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class CollectiveIntelligenceReport(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.now)
    # gather_collective_intelligence()'ın çıktısı
    result: dict | None = None
