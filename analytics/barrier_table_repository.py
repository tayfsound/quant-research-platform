"""Faz 268-sonrası — kullanıcı isteği: Adaptive Barrier Engine'i
RiskTargetStage'e wire edelim. AgentMemory/WeightRepository/
ConfidenceModelRepository ile AYNI dosya-tabanlı, tek "en son" tablo
deseni — öğrenilmiş bir artefakt, Class 2 audit verisi değil."""
import json
import os
from datetime import UTC, datetime
from pathlib import Path

_DEFAULT_STORAGE_PATH = os.environ.get("BARRIER_TABLE_STORAGE_PATH", "barrier_table_history")

# Bu oturumda daha önce doğrulanan (koşullu Adaptive Barrier OOS testi)
# AYNI gruplama — farklı bir gruplamayla kaydedilmiş bir tablo farklı bir
# şey ölçer, bu yüzden sabit tutuluyor.
GROUP_BY = ("direction", "regime", "volatility_regime")


class BarrierTableRepository:
    def __init__(self, storage_path: str = _DEFAULT_STORAGE_PATH):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(exist_ok=True)

    def save(self, table: dict, sample_count: int) -> None:
        payload = {
            "built_at": datetime.now(UTC).isoformat(),
            "sample_count": sample_count,
            "group_by": list(GROUP_BY),
            "table": table,
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
