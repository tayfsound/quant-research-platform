from dataclasses import dataclass, field
from typing import Any, Dict
from datetime import datetime


@dataclass(frozen=True)
class ReplaySnapshot:
    snapshot_id: str
    created_at: datetime

    market_state: Dict[str, Any] = field(default_factory=dict)
    portfolio_state: Dict[str, Any] = field(default_factory=dict)

    agent_weights: Dict[str, float] = field(default_factory=dict)
    beliefs: Dict[str, Any] = field(default_factory=dict)

    decision_state: Dict[str, Any] = field(default_factory=dict)
