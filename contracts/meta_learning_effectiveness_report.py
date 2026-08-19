"""Meta-Learning Effectiveness haftalık anlık görüntüsü — Cognitive Core
2.0 (Faz 744-768).

analytics/meta_learning_effectiveness.py::compute_meta_learning_trend()
gerçek zamanlı çağrılır (GET /meta-learning-effectiveness/) ama hiçbir
geçmişi yoktu — bu tablo periyodik (haftalık) anlık görüntüleri
saklıyor, Self-Model/Causal Inference/Collective Intelligence/MAE-MFE
Confidence ile AYNI desen.

Kasıtlı olarak SADECE tespit/rapor — hiçbir tuning kararını otomatik
onaylamıyor/uygulamıyor."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class MetaLearningEffectivenessReport(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.now)
    # gather_meta_learning_effectiveness()'ın çıktısı
    result: dict | None = None
