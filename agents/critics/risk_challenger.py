"""Risk Challenger Agent — kararları eleştiren risk katmanı."""

from contracts.agent import (
    AgentChallenge,
    AgentDomain,
    AgentOpinion,
)


class RiskChallenger:
    """
    Executive karar öncesi risk sorgulaması yapar.

    Görevi:
    - Kararı veto etmek değil
    - Kör noktaları göstermek
    - Risk sinyalleri üretmek
    """

    def __init__(self):
        self.domain = AgentDomain.RISK

    def challenge(
        self,
        opinion: AgentOpinion,
        context: dict,
    ) -> list[AgentChallenge]:

        challenges = []

        volatility = context.get("volatility", 0.0)
        confidence = opinion.confidence

        # Aşırı güven + yüksek volatilite
        if volatility > 0.7 and confidence > 0.75:
            challenges.append(
                AgentChallenge(
                    challenger_domain=AgentDomain.RISK,
                    target_domain=opinion.domain,
                    reason="Yüksek volatilite döneminde yüksek güven",
                    confidence=0.8,
                    evidence_strength=0.7,
                )
            )

        # Yön kalabalığı riski — Faz 268-sonrası kullanıcı bulgusu: bu
        # kontrol önceden opinion.direction'a BAKMADAN her ajanı (kalabalığa
        # hiç katılmayan azınlık/muhalif ses dahil) cezalandırıyordu.
        # "Sürü davranışı" kavramsal olarak sadece KALABALIĞA katılan
        # görüşler için anlamlı — sadece o yöndeki opinion hedefleniyor.
        crowding = context.get("crowding_risk", 0.0)
        crowded_direction = context.get("crowded_direction")

        if crowding > 0.6 and crowded_direction is not None and opinion.direction == crowded_direction:
            challenges.append(
                AgentChallenge(
                    challenger_domain=AgentDomain.RISK,
                    target_domain=opinion.domain,
                    reason="Olası kalabalık / sürü davranışı riski",
                    confidence=0.75,
                    evidence_strength=0.6,
                )
            )

        # Veri kalitesi düşükse
        if opinion.data_quality < 0.5:
            challenges.append(
                AgentChallenge(
                    challenger_domain=AgentDomain.RISK,
                    target_domain=opinion.domain,
                    reason="Kararı destekleyen veri kalitesi düşük",
                    confidence=0.7,
                    evidence_strength=0.5,
                )
            )

        return challenges
