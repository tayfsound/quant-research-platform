"""Historical Analog Engine (FIL Faz D) haftalık anlık görüntüsü — Faz 394.

analytics/historical_analog_engine.py::compute_historical_analogs()
canlı çağrıldığında 1831+ kapanmış kararı taraması gerekiyor — karar
döngüsü için pahalı. Bu tablo, Causal Inference/Agent Combination
Reliability ile AYNI desende haftalık bir anlık görüntü saklıyor;
engines/cognitive_pipeline.py::HistoricalAnalogOverrideStage bunun
SADECE son kaydedilmiş satırını okur (ucuz DB sorgusu)."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class HistoricalAnalogReport(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.now)
    # gather_historical_analogs()'ın çıktısı: {"analogs": [...], "baseline_win_rate": float, ...}
    result: dict | None = None
