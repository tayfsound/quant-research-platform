"""Agent Combination Reliability haftalık anlık görüntüsü — Faz 331.

analytics/agent_combination_reliability.py::compute_pairwise_combination_
reliability() gerçek zamanlı çalışır (GET /agent-combination-reliability/)
ama hiçbir geçmişi yoktu — bu tablo periyodik (haftalık) anlık görüntüleri
saklıyor, Causal Inference/Agent Ablation ile AYNI desen.

Kasıtlı olarak SADECE tespit/rapor — council'in hiçbir kararını
etkilemiyor, hiçbir pozisyon/risk/ajan-ağırlık kararını otomatik
değiştirmiyor."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AgentCombinationReliabilityReport(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.now)
    # gather_agent_combination_reliability()'in çıktısı: {"pairs": [...], "baseline_win_rate": ..., ...}
    result: dict | None = None
