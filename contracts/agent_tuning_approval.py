"""Agent tuning approval contract — Faz 239-241.

contracts/weight_approval.py ile AYNI insan-onay-kapısı deseni — ama
ağırlıklar yerine bir ajanın KENDİ iç skorlama katsayıları (θ) için.
Yeni θ, walk-forward out-of-sample Sharpe'ı geçip (services/
meta_learning_scheduler.py::MIN_SHARPE_IMPROVEMENT) VE bir insan
onaylamadan canlıya asla uygulanmıyor."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AgentTuningApproval(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.now)
    agent_id: str = ""
    proposed_coefficients: dict = Field(default_factory=dict)
    previous_coefficients: dict = Field(default_factory=dict)
    in_sample_sharpe: float = 0.0
    mean_oos_sharpe_tuned: float = 0.0
    mean_oos_sharpe_baseline: float = 0.0
    sharpe_improvement: float = 0.0
    sample_count: int = 0
    status: str = "pending"  # pending | approved | rejected
    approved_by: str = ""
    expires_at: datetime | None = None
    decided_at: datetime | None = None
