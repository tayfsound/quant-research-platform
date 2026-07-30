from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReplayResult:
    success: bool
    verified: bool

    original_decision: dict[str, Any]
    replayed_decision: dict[str, Any]

    differences: dict[str, Any]
