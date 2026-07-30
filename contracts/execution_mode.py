"""Agent Capability Boundary — frozen permission, mode authority."""
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ExecutionMode(StrEnum):
    EXPERIMENT = "experiment"
    PAPER = "paper"
    LIVE = "live"

class Permission(BaseModel):
    model_config = ConfigDict(frozen=True)
    can_place_orders: bool = False
    can_access_exchange: bool = False
    can_modify_risk_limits: bool = False
    can_run_unlimited_experiments: bool = True

PERMISSIONS: dict[ExecutionMode, Permission] = {
    ExecutionMode.EXPERIMENT: Permission(),
    ExecutionMode.PAPER: Permission(can_place_orders=True),
    ExecutionMode.LIVE: Permission(
        can_place_orders=True,
        can_access_exchange=True,
        can_modify_risk_limits=False,
        can_run_unlimited_experiments=False,
    ),
}

def get_permission(mode: ExecutionMode) -> Permission:
    return PERMISSIONS.get(mode, Permission())

class ExecutionAuthority(BaseModel):
    """Mode değişikliği yetkisi. AI doğrudan LIVE'a geçemez."""
    current_mode: ExecutionMode
    requested_mode: ExecutionMode
    approved: bool = False
    approved_by: str = ""
    signature: str = ""

    def can_escalate_to(self, target: ExecutionMode) -> bool:
        """EXPERIMENT → PAPER → LIVE zinciri sadece yetkiyle."""
        if target == ExecutionMode.EXPERIMENT:
            return True  # Her zaman deney yapabilir
        if target == ExecutionMode.PAPER:
            return self.approved and self.approved_by != ""
        if target == ExecutionMode.LIVE:
            return self.approved and self.signature != ""
        return False
