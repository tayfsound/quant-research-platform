"""Self-Model haftalık öz-güvenilirlik anlık görüntüsü — Cognitive Core 3.0.

analytics/self_model.py::compute_self_reliability_snapshot() gerçek zamanlı
çalışır (GET /self-model/) ama hiçbir geçmişi yoktu — bu tablo periyodik
(haftalık) anlık görüntüleri saklıyor, Calibration/Feature IC ile AYNI desen.

Kasıtlı olarak SADECE ölçüm/rapor — council'in hiçbir kararını etkilemiyor,
hiçbir risk parametresini otomatik değiştirmiyor."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class SelfModelReport(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.now)
    # compute_self_reliability_snapshot()'ın çıktısı: {"overall_reliability", "reliability_flags", "inputs"}
    result: dict | None = None
