"""Causal Inference (Granger causality) haftalık anlık görüntüsü — Cognitive Core 4.0.

analytics/causal_inference.py::compute_granger_causality() gerçek zamanlı
çalışır (GET /causal-inference/) ama hiçbir geçmişi yoktu — bu tablo
periyodik (haftalık) anlık görüntüleri saklıyor, Self-Model/Calibration/
Feature IC ile AYNI desen.

Kasıtlı olarak SADECE tespit/rapor — council'in hiçbir kararını
etkilemiyor, hiçbir pozisyon/risk kararını otomatik değiştirmiyor."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class CausalInferenceReport(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.now)
    # gather_causal_relationships()'in çıktısı: {"relationships": [...], "symbols_tested": int, ...}
    result: dict | None = None
