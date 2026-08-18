"""MAE/MFE Bootstrap Güven Aralığı haftalık anlık görüntüsü — Cognitive
Core 2.0 (Faz 469-493).

analytics/mae_mfe_scientific.py::bootstrap_quantile_ci() gerçek zamanlı
çalışır (GET /mae-mfe-confidence/) ama hiçbir geçmişi yoktu — bu tablo
periyodik (haftalık) anlık görüntüleri saklıyor, Self-Model/Causal
Inference/Collective Intelligence ile AYNI desen.

Kasıtlı olarak SADECE ölçüm/rapor — hiçbir SL/TP kararını otomatik
değiştirmiyor."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class MaeMfeConfidenceReport(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.now)
    # gather_mae_mfe_confidence()'ın çıktısı
    result: dict | None = None
