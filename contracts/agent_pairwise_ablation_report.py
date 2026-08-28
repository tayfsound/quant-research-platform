"""Agent Interaction (pairwise ablation) haftalık anlık görüntüsü — Faz
368-devam. agent_ablation_report.py ile AYNI generic desen.

Kasıtlı olarak SADECE ölçüm/rapor — hiçbir ajanın canlı oy hakkını
otomatik değiştirmiyor, karar hattına bağlanmıyor."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AgentPairwiseAblationReport(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.now)
    # gather_agent_pairwise_ablation()'ın çıktısı
    result: dict | None = None
