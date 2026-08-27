"""OnChain BTC-Kısıtı Uzatma Karşı-Olgusalı — backlog #51, saf hesaplama
katmanı.

Faz 248 bulgusu: `agents/onchain_agent.py`'nin network_activity_trend/
hash_rate_trend puanları (Bitcoin zincirine özel) bilerek SADECE BTC
işlem görürken yön puanına katılıyor — önceden TÜM sembollere aynen
uygulanıyordu, bu bir hataydı. Kullanıcı sorusu (2026-08-26): "bu
kısıtlama açılsaydı ne olurdu — BTC ağ sağlığı genel bir risk-on/risk-
off göstergesi gibi kullanılsaydı?"

Bu modül, `analytics/agent_ablation.py::resynthesize_belief_and_
opinions_with_domain_excluded`'in AYNI ilkesi ama TERS yönde bir
operasyon: bir domain'i SIFIRLAMAK yerine, o karardaki onchain oyuna
GERÇEK bir BTC kararından alınmış network_activity_trend/hash_rate_
trend katkılarını EKLEYİP council'i yeniden sentezliyor —
agents/onchain_agent.py'nin BİREBİR AYNI skorlama eşikleri (>0.4 LONG,
<-0.4 SHORT, confidence=min(|score|/5, 0.85)) kopyalanmadan, doğrudan
kullanılıyor (tek kaynak orada, burada tekrarlanmıyor — DEĞİL, burada
KOPYALANMAK ZORUNDA çünkü ajanın kendisi context nesnesi bekliyor, ham
sözlük değil; eşikler agents/onchain_agent.py ile YORUM SATIRINDA
senkron tutulmalı).

Kasıtlı olarak SADECE ölçüm — hiçbir ajanın canlı oy hakkını burada
otomatik değiştirmiyor (agent_ablation.py ile AYNI ilke)."""
from contracts.agent import AgentDomain

# agents/onchain_agent.py'nin BİREBİR AYNI eşikleri — değişirse burası da
# güncellenmeli (tek gerçek kaynak orası, burası bilinçli bir kopya).
_LONG_THRESHOLD = 0.4
_SHORT_THRESHOLD = -0.4
_CONFIDENCE_DIVISOR = 5.0
_MAX_CONFIDENCE = 0.85


def resynthesize_with_onchain_btc_extension(
    agent_contributions: list[dict],
    network_activity_trend_contribution: float,
    hash_rate_trend_contribution: float,
):
    """agent_contributions: BTC-DIŞI bir kararın gerçek kayıtlı oyları.
    network_activity_trend_contribution/hash_rate_trend_contribution:
    en yakın zamanlı GERÇEK bir BTC kararının onchain oyunun kendi
    feature_contributions'ından alınmış ±0.5'lik gerçek katkılar (0.0 =
    o cycle'da BTC'de de bu sinyal tetiklenmemiş).

    Bu kararda onchain hiç oy kullanmamışsa (data_unavailable_domains)
    ya da zaten is_btc=True skorlanmışsa (yani BTCUSDT'nin kendisiyse —
    bu senaryo zaten geçerli, karşı-olgusal anlamsız) None döner."""
    from analytics.agent_ablation import reconstruct_opinions
    from services.belief_engine import BeliefEngine

    opinions = reconstruct_opinions(agent_contributions)
    if not opinions:
        return None
    onchain_opinion = next((o for o in opinions if o.domain == AgentDomain.ONCHAIN), None)
    if onchain_opinion is None:
        return None

    existing_contributions = dict(onchain_opinion.feature_contributions)
    if "network_activity_trend" in existing_contributions or "hash_rate_trend" in existing_contributions:
        return None  # zaten BTC (is_btc=True) — karşı-olgusal senaryo geçerli değil

    new_contributions = dict(existing_contributions)
    if network_activity_trend_contribution:
        new_contributions["network_activity_trend"] = network_activity_trend_contribution
    if hash_rate_trend_contribution:
        new_contributions["hash_rate_trend"] = hash_rate_trend_contribution
    if new_contributions == existing_contributions:
        return None  # o an BTC'de de her iki sinyal nötrdü, eklenecek bir şey yok

    score = sum(new_contributions.values())
    if score > _LONG_THRESHOLD:
        new_direction = "LONG"
    elif score < _SHORT_THRESHOLD:
        new_direction = "SHORT"
    else:
        new_direction = "WAIT"
    new_confidence = round(min(abs(score) / _CONFIDENCE_DIVISOR, _MAX_CONFIDENCE), 3)

    extended_opinion = onchain_opinion.model_copy(deep=True)
    extended_opinion.direction = new_direction
    extended_opinion.confidence = new_confidence
    extended_opinion.feature_contributions = {k: round(v, 4) for k, v in new_contributions.items()}
    extended_opinion.recalculate()

    adjusted = [extended_opinion if o.domain == AgentDomain.ONCHAIN else o for o in opinions]
    belief = BeliefEngine().synthesize(adjusted)
    return belief, adjusted
