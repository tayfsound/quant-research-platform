"""Inner Critic — alternatif açıklamalar ve karşı argümanlar üretir.

Faz 268-sonrası — kritik bulgu (üçüncü taraf mimari incelemesi + gerçek
kod doğrulaması): bu sınıf DecisionFusion.__init__'te instantiate
ediliyordu (self.critic = InnerCritic()) ama .review() hiçbir yerde
ÇAĞRILMIYORDU — üretilen challenges/risk_flags/improvements tamamen ölü
koddu. Artık review()'un çıktısı, DecisionFusion.evaluate()'te GERÇEKTEN
confidence/final_size'ı etkiliyor (bkz. decision_fusion.py). Bunun için
review() artık ham metin/etiket listelerinin YANINDA, doğrudan
uygulanabilir iki sayısal alan da döndürüyor — DecisionFusion'ın
risk_flags string'lerini "magic string" olarak yorumlamasına gerek
kalmasın diye:
- confidence_multiplier: [0.5, 1.0] aralığında, sadece hafıza kaynaklı
  yön çelişkisi (direction_conflict) varken 1.0'dan düşük. Çarpan,
  çelişen hafıza örüntüsünün KENDİ confidence'ıyla orantılı — zayıf bir
  geçmiş örüntü (düşük insight confidence) neredeyse hiç indirim
  yapmamalı, güçlü bir çelişen örüntü ise anlamlı ama asla %50'den
  fazla olmayan bir indirim yapmalı (tek bir sinyal confidence'ı sıfıra
  çekmemeli).
- size_multiplier: yüksek volatilite (ATR>3) durumunda 0.7 — bu sayı
  icat edilmedi, kodun zaten ürettiği ama hiç uygulanmayan "Reduce
  position by 30%" önerisinin GERÇEKTEN uygulanmış hali."""
from contracts.context import CognitiveCycleContext

_HIGH_VOLATILITY_SIZE_MULTIPLIER = 0.7
_MAX_DIRECTION_CONFLICT_DISCOUNT = 0.5


class InnerCritic:
    def review(self, ctx: CognitiveCycleContext) -> dict:
        features = ctx.market.features
        challenges = []
        improvements = []
        risk_flags = []
        alternative_explanations = []
        missing_information = []
        confidence_multiplier = 1.0
        size_multiplier = 1.0

        rsi = features.get("RSI", 50)
        atr = features.get("ATR", 1)

        # Volatilite kontrolü
        if atr > 3:
            challenges.append("High volatility — position sizing may need adjustment")
            improvements.append("Reduce position by 30%")
            risk_flags.append("high_volatility")
            alternative_explanations.append("Price move may be noise, not signal")
            size_multiplier *= _HIGH_VOLATILITY_SIZE_MULTIPLIER

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
            if insight.get("dominant_direction") is not None and insight.get("dominant_direction") != ctx.decision.proposed_direction:
                challenges.append(f"Memory suggests {insight.get('dominant_direction')} but proposal is {ctx.decision.proposed_direction}")
                risk_flags.append("direction_conflict")
                alternative_explanations.append("Historical pattern contradicts current proposal — reconsider")
                insight_confidence = max(0.0, min(1.0, insight.get("confidence", 0) or 0))
                confidence_multiplier *= 1.0 - _MAX_DIRECTION_CONFLICT_DISCOUNT * insight_confidence

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
            "confidence_multiplier": round(confidence_multiplier, 4),
            "size_multiplier": round(size_multiplier, 4),
        }
