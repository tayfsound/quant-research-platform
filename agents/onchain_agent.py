"""OnChain Agent — zincir üstü verilerden yön çıkarır."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.onchain import OnChainContext


class OnChainAgent:
    def __init__(self):
        self.agent_id = "onchain_agent_v1"

    def analyze(self, context: OnChainContext) -> AgentOpinion:
        evidence = []
        caveats = []
        score = 0.0

        # Exchange akışı
        if context.exchange_outflow_24h > context.exchange_inflow_24h * 1.5:
            score += 1.5
            evidence.append("Strong exchange outflow — coins leaving exchanges")
        elif context.exchange_inflow_24h > context.exchange_outflow_24h * 1.5:
            score -= 1.5
            evidence.append("Strong exchange inflow — potential selling pressure")

        # Balina aktivitesi
        if context.whale_accumulation and context.whale_distribution:
            caveats.append("Conflicting whale signals detected — accumulation and distribution simultaneously")
        elif context.whale_accumulation:
            score += 1.5
            evidence.append("Whale accumulation detected")
        elif context.whale_distribution:
            score -= 1.5
            evidence.append("Whale distribution detected")

        # Stablecoin arzı
        if context.stablecoin_mint_24h > 100_000_000:
            score += 1.0
            evidence.append(f"Significant stablecoin minting (${context.stablecoin_mint_24h:,.0f}) — potential buying power")

        # Uyuyan coin'ler
        if context.dormant_coins_moved:
            caveats.append("Dormant coins moved — potential market anomaly")

        # MVRV Z-Score
        if context.mvrv_zscore > 3.0:
            score -= 2.0
            evidence.append(f"MVRV Z-Score extremely high ({context.mvrv_zscore}) — market overvalued")
        elif context.mvrv_zscore < -1.0:
            score += 2.0
            evidence.append(f"MVRV Z-Score extremely low ({context.mvrv_zscore}) — market undervalued")

        if score > 0.5:
            direction = "LONG"
        elif score < -0.5:
            direction = "SHORT"
        else:
            direction = "WAIT"

        confidence = min(abs(score) / 5.0, 0.85)

        return AgentOpinion(
            agent_id=self.agent_id,
            domain=AgentDomain.ONCHAIN,
            direction=direction,
            confidence=round(confidence, 3),
            evidence_strength=0.75,
            data_quality=0.80,
            freshness=0.70,
            source_reliability=0.85,
            evidence=evidence,
            caveats=caveats,
        ).recalculate()
