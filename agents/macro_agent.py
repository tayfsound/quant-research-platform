"""Macro Agent — ekonomik göstergelerden piyasa yönü çıkarır."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.macro import MacroContext


class MacroAgent:
    def __init__(self):
        self.agent_id = "macro_agent_v1"

    def analyze(self, context: MacroContext) -> AgentOpinion:
        evidence = []
        caveats = []
        score = 0.0

        # Enflasyon
        if context.inflation_trend == "rising":
            score -= 1.0
            evidence.append("Inflation pressure increasing")
        elif context.inflation_trend == "falling":
            score += 1.0
            evidence.append("Inflation cooling")

        # Likidite — Faz 215: gerçek bulgu — sadece "tight" cezalandırılıyordu,
        # "loose" (genişleyen M2 para arzı — tarihsel olarak risk
        # varlıkları için destekleyici) hiç ödüllendirilmiyordu. Asimetrik:
        # ajan likiditenin sadece kötü tarafını görebiliyordu.
        if context.liquidity_condition == "tight":
            score -= 1.0
            evidence.append("Liquidity conditions restrictive")
        elif context.liquidity_condition == "loose":
            score += 1.0
            evidence.append("Liquidity conditions expansionary")

        # Merkez bankası
        if context.central_bank_bias == "hawkish":
            score -= 1.0
            evidence.append("Central bank stance hawkish")
        elif context.central_bank_bias == "dovish":
            score += 1.0
            evidence.append("Central bank stance supportive")

        # İstihdam
        if context.employment_trend == "weakening":
            score -= 0.5
            evidence.append("Employment trend weakening")

        if score > 0:
            direction = "LONG"
        elif score < 0:
            direction = "SHORT"
        else:
            direction = "WAIT"

        confidence = min(abs(score) / 3.0, 1.0)

        return AgentOpinion(
            agent_id=self.agent_id,
            domain=AgentDomain.MACRO,
            direction=direction,
            confidence=round(confidence, 3),
            evidence_strength=0.7,
            data_quality=0.8,
            freshness=0.9,
            source_reliability=0.9,
            evidence=evidence,
            caveats=caveats,
        ).recalculate()
