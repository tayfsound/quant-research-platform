"""Sentiment Agent V1.1 — düzeltilmiş yorumlar, News Tone, Google Trends."""
from contracts.agent import AgentOpinion, AgentDomain
from contracts.sentiment import SentimentContext

class SentimentAgent:
    def __init__(self):
        self.agent_id = "sentiment_agent_v1"

    def analyze(self, context: SentimentContext) -> AgentOpinion:
        evidence = []
        caveats = []
        score = 0.0

        # Fear & Greed — contrarian yorum
        if context.fear_greed_index < 25:
            score += 2.0
            evidence.append(f"Extreme fear detected ({context.fear_greed_index})")
            evidence.append("Contrarian interpretation: possible accumulation zone")
        elif context.fear_greed_index > 75:
            score -= 2.0
            evidence.append(f"Extreme greed detected ({context.fear_greed_index})")
            evidence.append("Contrarian interpretation: possible distribution zone")
        elif context.fear_greed_index < 40:
            score += 0.5
            evidence.append(f"Fear elevated ({context.fear_greed_index})")

        # Sosyal medya tonu
        if context.social_media_sentiment < -0.3:
            score += 1.0
            evidence.append("Social media sentiment extremely negative — contrarian signal")
        elif context.social_media_sentiment > 0.5:
            score -= 0.5
            evidence.append("Social media euphoric — caution")

        # Haber tonu
        if context.news_tone == "negative":
            score += 0.3
            evidence.append("Negative news tone indicates bearish crowd positioning")
        elif context.news_tone == "positive":
            score -= 0.3
            evidence.append("Positive news tone — may be overbought")

        # Google Trends
        if context.google_trends_score > 80:
            score -= 0.2
            evidence.append("Extreme search interest may indicate retail overheating")
        elif context.google_trends_score < 20:
            score += 0.2
            evidence.append("Low search interest — potential undervaluation")

        # Volatilite
        if context.volatility_index > 30:
            caveats.append(f"High volatility ({context.volatility_index}) — position sizing critical")
            score = score * 0.7

        # Piyasa pozisyonlanması
        if context.positioning == "short_bias":
            score += 1.0
            evidence.append("Market heavily short — squeeze potential")
        elif context.positioning == "long_bias":
            score -= 1.0
            evidence.append("Market heavily long — downside risk")

        # Self-bias farkındalığı
        caveats.append("Sentiment signals are reflexive and crowd-dependent")

        if score > 0.5:
            direction = "LONG"
        elif score < -0.5:
            direction = "SHORT"
        else:
            direction = "WAIT"

        confidence = min(abs(score) / 4.0, 0.85)

        return AgentOpinion(
            agent_id=self.agent_id,
            domain=AgentDomain.SENTIMENT,
            direction=direction,
            confidence=round(confidence, 3),
            evidence_strength=0.65,
            data_quality=0.75,
            freshness=0.85,
            source_reliability=0.7,
            evidence=evidence,
            caveats=caveats,
        ).recalculate()
