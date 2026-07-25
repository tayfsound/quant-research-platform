"""Inner Critic — alternatif açıklamalar ve karşı argümanlar üretir."""
from contracts.context import CognitiveCycleContext

class InnerCritic:
    def review(self, ctx: CognitiveCycleContext) -> dict:
        features = ctx.market.features
        challenges = []
        improvements = []
        risk_flags = []
        alternative_explanations = []
        missing_information = []

        rsi = features.get("RSI", 50)
        atr = features.get("ATR", 1)

        # Volatilite kontrolü
        if atr > 3:
            challenges.append("High volatility — position sizing may need adjustment")
            improvements.append("Reduce position by 30%")
            risk_flags.append("high_volatility")
            alternative_explanations.append("Price move may be noise, not signal")

        # RSI aşırı bölge
        if rsi < 20:
            challenges.append("RSI extremely oversold — dead cat bounce risk")
            alternative_explanations.append("This could be the start of a deeper decline, not a buying opportunity")
            missing_information.append("Is there fundamental news driving this sell-off?")
        elif rsi > 80:
            challenges.append("RSI extremely overbought")
            alternative_explanations.append("Momentum may continue — tops are a process, not a point")

        # Hafıza çelişkisi
        memory_insights = [item for item in ctx.cognition.relevant_knowledge if item.get("type") == "memory_insight"]
        if memory_insights:
            insight = memory_insights[-1]["data"]
            if insight.get("confidence", 0) < 0.3:
                challenges.append("Historical pattern confidence is low")
                missing_information.append("Not enough similar historical episodes for reliable inference")
            if insight.get("dominant_direction") != ctx.decision.proposed_direction:
                challenges.append(f"Memory suggests {insight.get('dominant_direction')} but proposal is {ctx.decision.proposed_direction}")
                risk_flags.append("direction_conflict")
                alternative_explanations.append(f"Historical pattern contradicts current proposal — reconsider")

        # Hacim teyidi
        volume_ratio = features.get("volume_ratio", 1)
        if volume_ratio < 0.5:
            missing_information.append("Volume confirmation missing — low conviction signal")

        return {
            "objections": challenges,
            "alternative_explanations": alternative_explanations,
            "missing_information": missing_information,
            "improvements": improvements,
            "risk_flags": risk_flags,
        }
