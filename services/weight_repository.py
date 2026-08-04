"""Weight Repository — snapshot'ları JSON dosyasında saklar."""
import json
from pathlib import Path

from contracts.agent_weight_snapshot import AgentWeightSnapshot


class WeightRepository:
    def __init__(self, storage_path: str = "weight_history"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(exist_ok=True)

    def save(self, snapshot: AgentWeightSnapshot) -> AgentWeightSnapshot:
        filename = self.storage_path / f"snapshot_{snapshot.id}.json"
        filename.write_text(snapshot.model_dump_json(indent=2))
        # index
        index_file = self.storage_path / "index.json"
        index = []
        if index_file.exists():
            index = json.loads(index_file.read_text())
        index.append({
            "id": str(snapshot.id),
            "timestamp": snapshot.timestamp.isoformat(),
            "hash": snapshot.snapshot_hash,
        })
        index_file.write_text(json.dumps(index, indent=2))
        return snapshot

    def get_latest(self) -> AgentWeightSnapshot | None:
        index_file = self.storage_path / "index.json"
        if not index_file.exists():
            return None
        index = json.loads(index_file.read_text())
        if not index:
            return None
        latest_id = index[-1]["id"]
        filename = self.storage_path / f"snapshot_{latest_id}.json"
        if not filename.exists():
            return None
        return AgentWeightSnapshot.model_validate_json(filename.read_text())

    def get_by_id(self, snapshot_id) -> AgentWeightSnapshot | None:
        """Fetch a specific pinned snapshot — needed so a backtest run can
        use the weights that existed at a given historical point instead of
        whatever is 'latest' right now (get_latest() would leak future
        learning into a simulated past decision)."""
        filename = self.storage_path / f"snapshot_{snapshot_id}.json"
        if not filename.exists():
            return None
        return AgentWeightSnapshot.model_validate_json(filename.read_text())
