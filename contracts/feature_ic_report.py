"""Feature IC (Information Coefficient) haftalık rapor kaydı — Faz 268-sonrası.

Kullanıcı isteği: "Feature IC'yi karar hattına bağlama" yol haritası
maddesi — analytics/feature_ic.py::compute_feature_ic() gerçek zamanlı
(GET /feature-ic/) zaten çalışıyordu ama hiçbir GEÇMİŞİ yoktu; her sorgu
o anki durumu gösteriyordu, "IC zamanla nasıl değişti" sorusu
cevaplanamıyordu. Bu tablo periyodik (haftalık) anlık görüntüleri
saklıyor — llm_audit_runs (Faz 271) ile AYNI desen.

Kasıtlı olarak SADECE ölçüm/kayıt katmanı — hiçbir feature'ı otomatik
pasifleştirmiyor (feature_ic.py'nin kendi ilkesiyle aynı: "AI kendi
skorlama mantığını otomatik gevşetemez/değiştiremez"). Gerçek veri
birikip (şu an sadece ~23 kapanmış işlemde feature_contributions var,
istatistiksel olarak anlamlı hiçbir bulgu yok) anlamlı bir örüntü
çıktığında, insan onaylı bir pasifleştirme akışı AYRI bir iş olarak
üzerine eklenebilir."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class FeatureICReport(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.now)
    # {feature_name: {"ic": float, "p_value": float, "sample_size": int, "agent_domain": str}}
    features: dict = Field(default_factory=dict)
    total_closed_trades: int = 0
