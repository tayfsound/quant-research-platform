from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ReplayEvent:
    event_id: str
    timestamp: datetime
    event_type: str
    payload: dict[str, Any]
