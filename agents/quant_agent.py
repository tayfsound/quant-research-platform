"""Quant Agent — istatistiksel/kantitatif sinyal uzmanı."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.quant import QuantContext


class QuantAgent:
    def __init__(self):
        self.agent_id = "quant_agent_v1"

    def analyze(self, context: QuantContext) -> AgentOpinion:
        evidence = []
        caveats = []
        score = 0.0

        # Hurst exponent rejimi belirler: <0.5 mean-reverting, >0.5 trending
        mean_reverting_regime = context.hurst_exponent < 0.45
        trending_regime = context.hurst_exponent > 0.55

        if mean_reverting_regime:
            evidence.append(f"Hurst exponent {context.hurst_exponent:.2f} — mean-reverting regime")
            # Mean-reversion rejiminde z-score'un TERSİNE bahis
            if context.zscore <= -2.0:
                score += 2.0
                evidence.append(f"Z-score {context.zscore:.2f} — statistically oversold")
            elif context.zscore >= 2.0:
                score -= 2.0
                evidence.append(f"Z-score {context.zscore:.2f} — statistically overbought")
        elif trending_regime:
            evidence.append(f"Hurst exponent {context.hurst_exponent:.2f} — trending regime")
            # Trend rejiminde otokorelasyonun YÖNÜNDE bahis (momentum devam eder varsayımı)
            if context.autocorrelation > 0.3:
                score += 1.5
                evidence.append(f"Positive autocorrelation {context.autocorrelation:.2f} — momentum continuation")
            elif context.autocorrelation < -0.3:
                score -= 1.5
                evidence.append(f"Negative autocorrelation {context.autocorrelation:.2f} — momentum continuation")
        else:
            caveats.append(f"Hurst exponent {context.hurst_exponent:.2f} — near random walk, no statistical edge")

        # Aşırı volatilite — güveni azalt
        if context.realized_vol_percentile > 90:
            caveats.append(f"Realized volatility at {context.realized_vol_percentile:.0f}th percentile — reduced statistical reliability")
            score *= 0.6

        if score > 0.5:
            direction = "LONG"
        elif score < -0.5:
            direction = "SHORT"
        else:
            direction = "WAIT"

        confidence = min(abs(score) / 4.0, 0.85)

        return AgentOpinion(
            agent_id=self.agent_id,
            domain=AgentDomain.QUANT,
            direction=direction,
            confidence=round(confidence, 3),
            evidence_strength=0.75,
            data_quality=0.85,
            freshness=0.9,
            source_reliability=0.8,
            evidence=evidence,
            caveats=caveats,
        ).recalculate()
