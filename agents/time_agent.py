"""Time Agent — zamansal/seansal risk uzmanı.

Dürüstlük notu: zaman kendi başına yön tahmin etmez. Bu ajan kanıtlanmamış
"Pazartesi etkisi" gibi yön sinyalleri uydurmuyor — sadece bilinen
likidite/volatilite risklerini (funding saati yakınlığı, hafta sonu düşük
likidite) işaretleyip WAIT-ağırlıklı bir görüş üretiyor. Katkısı yön değil,
council'in genel güvenini bu dönemlerde gerçekçi şekilde düşürmesi."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.time_context import TimeContext


class TimeAgent:
    def __init__(self):
        self.agent_id = "time_agent_v1"

    def analyze(self, context: TimeContext) -> AgentOpinion:
        evidence = []
        caveats = []
        confidence = 0.3  # Baz: zaman zayıf bir sinyal, her zaman düşük başlar

        if context.hours_to_funding <= 0.25:
            caveats.append(f"Funding settlement in {context.hours_to_funding * 60:.0f} minutes — volatility spike risk")
            confidence = 0.5
        else:
            evidence.append(f"{context.hours_to_funding:.1f}h to next funding settlement")

        if context.is_weekend:
            caveats.append("Weekend session — lower liquidity, wider slippage risk")
            confidence = max(confidence, 0.4)

        if context.session == "overlap":
            evidence.append("Session overlap (EU/US) — typically highest liquidity window")
        elif context.session == "unknown":
            caveats.append("Session could not be determined")

        return AgentOpinion(
            agent_id=self.agent_id,
            domain=AgentDomain.TIME,
            direction="WAIT",
            confidence=round(confidence, 3),
            evidence_strength=0.4,
            data_quality=0.95,  # zaman verisi her zaman tam/güvenilir
            freshness=1.0,
            source_reliability=0.9,
            evidence=evidence,
            caveats=caveats,
        ).recalculate()
