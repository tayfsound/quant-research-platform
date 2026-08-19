"""Direction Prediction v2 (Brier Score) haftalık anlık görüntüsü —
Cognitive Core 2.0 / M4 (Faz 519-543).

Kasıtlı olarak SADECE ölçüm/rapor — hiçbir canlı kararı otomatik
değiştirmiyor."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class DirectionPredictionV2Report(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.now)
    # gather_direction_prediction_v2()'ın çıktısı
    result: dict | None = None
