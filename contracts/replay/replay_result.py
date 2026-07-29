from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class ReplayResult:
    success: bool
    verified: bool

    original_decision: Dict[str, Any]
    replayed_decision: Dict[str, Any]

    differences: Dict[str, Any]
