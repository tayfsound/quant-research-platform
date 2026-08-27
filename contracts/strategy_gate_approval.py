"""Strategy Gate Approval contract — Faz 366. contracts/weight_approval.py
ile AYNI desen: propose → pending → approve/reject."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class StrategyGateApproval(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.now)
    strategy: str
    market_regime: str
    sample_size: int
    win_rate: float
    rest_win_rate: float
    delta_vs_rest: float
    p_value: float
    replicated_out_of_sample: bool | None = None
    # Faz 366-devam: "approved" kasıtlı olarak KULLANILMIYOR — "onaylı
    # strateji" yanlış okunuyordu (strateji iyi sanılıyordu, oysa
    # onaylanan şey o rejimde ENGELLENMESİ). blocked = insan onayıyla
    # canlı gate'te aktif, dismissed = insan inceleyip engellememeye
    # karar verdi (ya da süresi doldu).
    status: str = "pending"  # pending | blocked | dismissed
    approved_by: str = ""    # human or system
    expires_at: datetime | None = None
    decided_at: datetime | None = None
