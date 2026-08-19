"""Agent Ablation haftalık anlık görüntüsü — Faz 296.

Kasıtlı olarak SADECE ölçüm/rapor — hiçbir ajanın canlı oy hakkını
otomatik değiştirmiyor."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AgentAblationReport(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.now)
    # gather_agent_ablation()'ın çıktısı
    result: dict | None = None
