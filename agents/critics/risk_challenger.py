"""Risk Challenger Agent — kararları eleştiren risk katmanı."""

from contracts.agent import (
    AgentChallenge,
    AgentOpinion,
    AgentDomain,
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
                    reason="High confidence during elevated volatility",
                    confidence=0.8,
                    evidence_strength=0.7,
                )
            )

        # Yön kalabalığı riski
        crowding = context.get("crowding_risk", 0.0)

        if crowding > 0.6:
            challenges.append(
                AgentChallenge(
                    challenger_domain=AgentDomain.RISK,
                    target_domain=opinion.domain,
                    reason="Possible crowding / herd behavior risk",
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
                    reason="Low data quality supporting decision",
                    confidence=0.7,
                    evidence_strength=0.5,
                )
            )

        return challenges
