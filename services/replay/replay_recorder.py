import json
from pathlib import Path

from contracts.replay.replay_event import ReplayEvent


class ReplayRecorder:

    def __init__(self, storage_path: str = "storage/replay/events.json"):
        self.path = Path(storage_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: ReplayEvent):
        events = self.load()
        events.append({
            "event_id": event.event_id,
            "timestamp": event.timestamp.isoformat(),
            "event_type": event.event_type,
            "payload": event.payload,
        })

        self.path.write_text(
            json.dumps(events, indent=2, default=str),
            encoding="utf-8"
        )

    def load(self) -> list[dict]:
        if not self.path.exists():
            return []

        return json.loads(
            self.path.read_text(encoding="utf-8")
        )
