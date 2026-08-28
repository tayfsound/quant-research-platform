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
#
# Faz 368 — kullanıcı bulgusu: kripto işlem geçmişi hisse/emtia'dan
# ÇOK daha kalabalık olduğu için (direction, regime, volatility_regime)
# kovaları fiilen kripto tarafından kalibre ediliyordu — MSFT/GC=F gibi
# semboller kendi risk profiline göre DEĞİL, hangi kovaya denk geldiyse
# ona göre (kripto-uygun) SL/TP oranı alıyordu. "asset_class" eklendi —
# services/agent_memory.py::asset_class_trading_category() ile AYNI kaba
# (crypto/commodity/equity) sınıflandırma kullanılıyor (asset_class_
# trading_gate'in de kullandığı TEK kaynak) — ince taneli sınıflandırma
# (gold_backed/precious_metal_future/equity/equity_index ayrı ayrı) veri
# seyrekliğinden dolayı min_group_size eşiğini geçemezdi.
GROUP_BY = ("direction", "regime", "volatility_regime", "asset_class")


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
