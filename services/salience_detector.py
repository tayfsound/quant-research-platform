"""Salience Detector — piyasa olayının önemini değerlendirir."""
from contracts.context import CognitiveCycleContext


class SalienceDetector:
    def __init__(self, threshold: float = 0.7):
        self.threshold = threshold

    def evaluate(self, ctx: CognitiveCycleContext) -> float:
        """
        Piyasa durumunun önem skorunu hesapla.
        < threshold → NO_ACTION, >= threshold → executive processing.
        """
        score = 0.0
        features = ctx.market.features

        # RSI aşırı bölgelerde
        rsi = features.get("RSI", 50)
        if rsi < 25 or rsi > 75:
            score += 0.3
        elif rsi < 30 or rsi > 70:
            score += 0.15

        # Volatilite yüksekse
        atr = features.get("ATR", 1)
        if atr > 3:
            score += 0.25
        elif atr > 2:
            score += 0.1

        # Hacim spike'ı varsa
        volume_ratio = features.get("volume_ratio", 1)
        if volume_ratio > 2:
            score += 0.2
        elif volume_ratio > 1.5:
            score += 0.1

        # Hafıza insight'ı varsa (benzer geçmiş durumlar)
        memory_insights = [
            item for item in ctx.cognition.relevant_knowledge
            if item.get("type") == "memory_insight"
        ]
        if memory_insights:
            insight = memory_insights[-1]["data"]
            if insight.get("similar_count", 0) >= 5:
                score += 0.15
            if insight.get("dominant_direction") != "NEUTRAL":
                score += 0.1

        return min(score, 1.0)  # max 1.0

    def should_act(self, ctx: CognitiveCycleContext) -> bool:
        return self.evaluate(ctx) >= self.threshold
