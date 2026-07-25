"""Dosya-tabanlı repository — atomik yazma."""
import json
import os
import tempfile
from pathlib import Path

from meta_optimizer.collector import ExperimentLog


class FileExperimentLogRepository:
    def __init__(self, log_path: str = "experiment_logs.json"):
        self.log_path = Path(log_path)
        self._logs: list[ExperimentLog] = []
        self._load()

    def _load(self):
        if not self.log_path.exists():
            return
        try:
            with open(self.log_path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            print("⚠️  Corrupted log file, starting fresh")
            data = []
        loaded = []
        for d in data:
            try:
                loaded.append(ExperimentLog(**d))
            except ValueError as e:
                print(f"⚠️  Skipping malformed log entry ({d.get('id', '?')}): {e}")
        self._logs = loaded

    def record(self, log: ExperimentLog) -> None:
        self._logs.append(log)
        self._save_atomic()

    def get_recent(self, n: int) -> list[ExperimentLog]:
        return self._logs[-n:]

    def count(self) -> int:
        return len(self._logs)

    def _save_atomic(self):
        try:
            fd, tmp_path = tempfile.mkstemp(dir=self.log_path.parent, prefix=self.log_path.name + ".")
            with os.fdopen(fd, "w") as f:
                json.dump([l.to_dict() for l in self._logs], f, indent=2, default=str)
            os.replace(tmp_path, self.log_path)
        except Exception as e:
            print(f"❌ Failed to save logs atomically: {e}")
