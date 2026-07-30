import json
from pathlib import Path

from contracts.replay.replay_snapshot import ReplaySnapshot


class SnapshotManager:

    def __init__(self, path="storage/replay/snapshots"):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)

    def save(self, snapshot: ReplaySnapshot):
        file = self.path / f"{snapshot.snapshot_id}.json"

        file.write_text(
            json.dumps(
                snapshot.__dict__,
                indent=2,
                default=str
            ),
            encoding="utf-8"
        )

    def load(self, snapshot_id: str):
        file = self.path / f"{snapshot_id}.json"

        if not file.exists():
            raise FileNotFoundError(snapshot_id)

        return json.loads(
            file.read_text(encoding="utf-8")
        )
