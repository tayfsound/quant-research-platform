"""Technical Agent — yapısal teknik analiz uzmanı."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.technical import TechnicalContext


class TechnicalAgent:
    def __init__(self):
        self.agent_id = "technical_agent_v1"

    def analyze(self, context: TechnicalContext) -> AgentOpinion:
        evidence = []
        caveats = []
        score = 0.0

        # Trend
        if context.trend == "bullish":
            score += 1.0
            evidence.append("Market in bullish trend")
        elif context.trend == "bearish":
            score -= 1.0
            evidence.append("Market in bearish trend")

        # Momentum
        if context.momentum == "strengthening" and context.trend == "bullish":
            score += 1.0
            evidence.append("Bullish momentum strengthening")
        elif context.momentum == "weakening" and context.trend == "bearish":
            score -= 1.0
            evidence.append("Bearish momentum strengthening")

        # Piyasa yapısı
        if context.market_structure == "higher_highs":
            score += 1.5
            evidence.append("Higher highs structure — bullish continuation pattern")
        elif context.market_structure == "lower_lows":
            score -= 1.5
            evidence.append("Lower lows structure — bearish continuation pattern")
        elif context.market_structure == "ranging":
            caveats.append("Market in consolidation — breakout needed for conviction")

        # EMA dizilimi
        if context.ema_alignment == "bullish_aligned":
            score += 0.5
            evidence.append("EMAs bullishly aligned")
        elif context.ema_alignment == "bearish_aligned":
            score -= 0.5
            evidence.append("EMAs bearishly aligned")

        # RSI aşırı bölgeler
        if context.rsi_value < 25:
            score += 1.0
            evidence.append(f"RSI extremely oversold ({context.rsi_value})")
        elif context.rsi_value > 75:
            score -= 1.0
            evidence.append(f"RSI extremely overbought ({context.rsi_value})")

        # Hacim teyidi
        if context.volume_confirmation and context.trend == "bullish":
            score += 0.5
            evidence.append("Volume confirms trend")
        elif not context.volume_confirmation:
            caveats.append("Volume not confirming trend — potential divergence")

        # Volatilite
        if context.volatility_regime == "high":
            caveats.append("High volatility regime — reduced position sizing recommended")

        if score > 0.5:
            direction = "LONG"
        elif score < -0.5:
            direction = "SHORT"
        else:
            direction = "WAIT"

        confidence = min(abs(score) / 5.0, 0.85)

        return AgentOpinion(
            agent_id=self.agent_id,
            domain=AgentDomain.TECHNICAL,
            direction=direction,
            confidence=round(confidence, 3),
            evidence_strength=0.70,
            data_quality=0.85,
            freshness=0.90,
            source_reliability=0.75,
            evidence=evidence,
            caveats=caveats,
        ).recalculate()
