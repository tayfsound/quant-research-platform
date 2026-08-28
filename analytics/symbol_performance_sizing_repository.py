"""Faz 368 — kullanıcı bulgusu: council SL zararları belirli sembol×yön
hücrelerinde sistematik olarak yoğunlaşıyor (ör. ATOMUSDT_LONG≈-38k).
analytics/self_correction_sizing_repository.py ile AYNI dosya-tabanlı,
tek "en son" anlık görüntü deseni — öğrenilmiş bir artefakt, Class 2
audit verisi değil, ayrı bir Alembic migration/DB tablosu YOK."""
import json
import os
from datetime import UTC, datetime
from pathlib import Path

_DEFAULT_STORAGE_PATH = os.environ.get("SYMBOL_PERFORMANCE_SIZING_STORAGE_PATH", "symbol_performance_sizing_history")


class SymbolPerformanceSizingRepository:
    def __init__(self, storage_path: str = _DEFAULT_STORAGE_PATH):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(exist_ok=True)

    def save(self, by_symbol_direction: dict) -> None:
        payload = {
            "built_at": datetime.now(UTC).isoformat(),
            "by_symbol_direction": by_symbol_direction,
        }
        (self.storage_path / "latest.json").write_text(json.dumps(payload, indent=2))

    def get_latest(self) -> dict | None:
        file = self.storage_path / "latest.json"
        if not file.exists():
            return None
        try:
            return json.loads(file.read_text())
        except (json.JSONDecodeError, OSError):
            return None
