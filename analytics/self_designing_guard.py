"""Self-Designing Intelligence Guard — Cognitive Core 11.0.

Bu oturumda eklenen öneri motorlarının (analytics/adaptive_barrier_engine.py,
analytics/moe_regime_router.py, compute_optimal_barrier) HİÇBİRİ şu an
canlı karar hattına bağlı değil — ama ileride biri bağlanacaksa, GERÇEK
bir insan-onay kapısından geçmesi gerekiyor. contracts/weight_approval.py
ve contracts/agent_tuning_approval.py bu deseni ZATEN kanıtlamış durumda:
approve() sadece require_role(Role.OPERATOR) korumalı bir API
endpoint'inden (api/rest/weights.py) çağrılabiliyor, hiçbir dahili kod
yolu kendi kendine onaylayamıyor — bu, gerçek koddan doğrulandı (grep
`.status = "approved"`: TEK yazma yolu WeightApprovalRepository.approve(),
ve o SADECE authenticated bir OPERATOR'dan çağrılıyor).

Bu modül, bu deseni AI'nin YENİ ürettiği herhangi bir öneri için
yeniden kullanılabilir, GENEL bir ilkel haline getiriyor — ileride bu
oturumdaki öneri motorlarından biri canlıya alınmak istendiğinde,
sıfırdan bir onay mekanizması icat etmek yerine burası kullanılabilir.

GÜVENLİK İLKESİ (proje kuralı): AI kendi mimarisini önerebilir/test
edebilir/kıyaslayabilir ama KENDİSİNE ASLA canlı deploy yetkisi veremez.
Bu, sadece bir yorum değil — approve()'un approved_by argümanı ZORUNLU
(varsayılanı yok) ve "ai"/"system"/"auto"/"bot" gibi insan-olmayan
kimliklerle çağrılırsa AÇIKÇA reddediliyor, Python seviyesinde
zorlanıyor."""
from dataclasses import dataclass
from datetime import UTC, datetime

_NON_HUMAN_IDENTITIES = frozenset({"ai", "system", "auto", "bot", "claude", "assistant"})


@dataclass
class AIProposal:
    proposal_type: str
    payload: dict
    status: str = "pending"
    approved_by: str | None = None
    decided_at: datetime | None = None

    def approve(self, approved_by: str) -> None:
        """approved_by BOŞ/None olamaz ve bilinen bir insan-olmayan
        kimlik olamaz — bu, dahili bir kod yolunun kendi kendini
        onaylamasını Python seviyesinde engelliyor, sadece bir
        sözleşme/yorum değil."""
        _validate_human_identity(approved_by)
        self.status = "approved"
        self.approved_by = approved_by
        self.decided_at = datetime.now(UTC)

    def reject(self, rejected_by: str) -> None:
        _validate_human_identity(rejected_by)
        self.status = "rejected"
        self.approved_by = rejected_by
        self.decided_at = datetime.now(UTC)


def _validate_human_identity(identity: str | None) -> None:
    if not identity or not identity.strip():
        raise ValueError("Bir AI önerisi ancak GERÇEK bir insan kimliğiyle onaylanabilir/reddedilebilir — kimlik boş olamaz")
    if identity.strip().lower() in _NON_HUMAN_IDENTITIES:
        raise ValueError(
            f"'{identity}' bir insan kimliği gibi görünmüyor — kendi kendine onay/red engellendi"
        )
