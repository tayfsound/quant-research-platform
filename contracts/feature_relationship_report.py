"""Feature Relationship haftalık rapor kaydı — Faz 368.

Kullanıcı isteği: Feature IC'deki (analytics/feature_ic.py) negatif IC'li
feature'ların (trend, EMA, momentum, VWAP — hepsi -%30 ila -%44 IC) "kötü
sinyal" değil, muhtemelen AYNI latent bilginin tekrar tekrar sayılması
olduğu şüphesi — gerçek veriyle doğrulandı (bkz. analytics/feature_
relationship.py docstring'i). Bu tablo periyodik (haftalık) redundancy
matrisi + koşullu IC anlık görüntülerini saklıyor — feature_ic_reports
(Faz 268-sonrası) ile AYNI desen.

Kasıtlı olarak SADECE ölçüm/kayıt katmanı — hiçbir feature'ı otomatik
pasifleştirmiyor, karar hattına bağlanmıyor."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class FeatureRelationshipReport(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.now)
    # {"{a}|{b}": {"correlation": float, "sample_size": int}}
    redundancy: dict = Field(default_factory=dict)
    # {feature: {"raw_ic": float, "conditional_ic_given": {other: float|None}}}
    conditional_ic: dict = Field(default_factory=dict)
    total_closed_trades: int = 0
