import hashlib
import json
from typing import Any


def create_decision_hash(data: dict[str, Any]) -> str:
    payload = json.dumps(
        data,
        sort_keys=True,
        default=str
    )

    return hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()
