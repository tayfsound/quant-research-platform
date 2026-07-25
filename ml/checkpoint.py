"""Model checkpoint ve rollback yönetimi."""
import pickle
from pathlib import Path


class CheckpointManager:
    def __init__(self, base_path: str = "checkpoints"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(exist_ok=True)

    def save(self, model, name: str):
        with open(self.base_path / f"{name}.pkl", "wb") as f:
            pickle.dump(model, f)

    def load(self, name: str):
        with open(self.base_path / f"{name}.pkl", "rb") as f:
            return pickle.load(f)
