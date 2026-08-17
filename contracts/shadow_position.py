"""Shadow Mode (Macro-Only karşılaştırma) — Faz 268-sonrası.

Kullanıcı bulgusu: 23 pozisyonluk örneklemde macro ajanının yönlü
tahminleri %86 isabetli görünüyordu — ama bu, council'i sadeleştirmek
için yeterli kanıt değil (survivorship bias + zaman çerçevesi çatışması
riski var, kullanıcıyla tartışıldı). Kullanıcıyla üzerinde anlaşılan
çerçeve: council'in GERÇEK kararlarını hiç etkilemeyen, SADECE macro'nun
kendi yönüne göre sanal (paper) pozisyon açıp kapatan izole bir gölge
takipçi (services/macro_shadow_tracker.py) — 100+ örneklem birikince
Council PnL vs Macro-Only PnL karşılaştırması gerçek veriyle yapılabilsin.

Kasıtlı olarak SADECE ölçüm — hiçbir gerçek kararı etkilemiyor, hiçbir
otomatik "council'i küçült" eylemi tetiklemiyor (Feature IC/LLM Audit ile
AYNI ilke: AI kendi karar mimarisini otomatik gevşetemez/değiştiremez)."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ShadowPosition(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    source: str = "macro"
    symbol: str
    direction: str
    confidence: float | None = None
    entry_price: float
    exit_price: float | None = None
    stop_loss_price: float
    take_profit_price: float
    status: str = "open"
    pnl_pct: float | None = None
    exit_reason: str | None = None
    opened_at: datetime = Field(default_factory=datetime.now)
    closed_at: datetime | None = None
