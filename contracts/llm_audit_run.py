"""LLM Sistem Denetimi çalışma kaydı — Faz 271."""
from datetime import datetime
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


class LLMAuditRun(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.now)
    response: str
    tool_calls: list[dict] = Field(default_factory=list)
    proposals_created: int = 0
    # Faz 282 — kullanıcı bulgusu: "Araç çağrı döngüsü sınırına ulaşıldı"
    # gibi teknik başarısızlıklar, gerçek bir denetim bulgusuyla (ya da
    # dürüst "sorun yok" cevabıyla) ayırt edilemiyordu — llm_reasoner.py::
    # ask_with_tools artık "ok"/"no_api_key"/"timeout"/"tool_loop_limit"/
    # "error" döndürüyor, burada olduğu gibi saklanıyor.
    status: str = "ok"
