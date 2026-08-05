"""Epistemology Domain Contracts — "ne kadar gerçekten biliyoruz" meta-bağlamı."""
from datetime import datetime

from pydantic import BaseModel, Field


class EpistemologyContext(BaseModel):
    """EpistemologyAgent için meta-bilgi bağlamı. Yön tahmini yapmaz —
    mevcut verinin ne kadar tam/taze olduğunu ölçüp, veri zayıfsa
    council'in genel güvenini (WAIT'e doğru) dengeleyen bir görüş üretir."""
    feature_completeness: float = 1.0   # 0..1, beklenen market feature'larından kaçının gerçekten mevcut olduğu
    data_age_seconds: float = 0.0
    known_unknown_count: int = 0        # Eksik/varsayılan değerde kalan feature sayısı
    timestamp: datetime = Field(default_factory=datetime.now)
