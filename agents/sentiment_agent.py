"""Sentiment Agent V1.1 — düzeltilmiş yorumlar, News Tone, Google Trends.

Faz 367-devam — kullanıcı kararıyla geri getirildi (2026-08-28): Faz 269'da
solo %5 isabetle kaldırılmıştı, ama Ajan Kombinasyonu Güvenilirliği'nin
(analytics/agent_combination_reliability.py) ölçtüğü GERÇEK geçmiş veri
gösterdi ki sentiment DİĞER ajanlarla BİRLİKTE anlaştığında çok güçlü
(pattern+sentiment %100, quant+sentiment %99.3, order_flow+sentiment
%98.2, sentiment+technical %98.0, macro+sentiment %89.3 — hepsi FDR'ı
geçmiş). Solo zayıf ama grupta güçlü bir ajanı eski (tamamen solo-doğruluk
tabanlı) ağırlıklandırma hiç fark edemezdi — services/weight_optimizer.py::
_compute_synergy_adjustments artık tam bunu düzeltiyor, bu yüzden geri
getirmek artık güvenli/anlamlı."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.sentiment import SentimentContext


class SentimentAgent:
    def __init__(self):
        self.agent_id = "sentiment_agent_v1"

    def analyze(self, context: SentimentContext) -> AgentOpinion:
        evidence = []
        caveats = []
        # Faz 268-sonrası: Feature Importance — bkz. agents/quant_agent.py
        # ve agents/technical_agent.py'deki aynı desen. scale_all, O ANA
        # KADAR birikmiş katkılara uygulanıyor — sonradan eklenen
        # positioning katkısı bundan ETKİLENMİYOR, orijinal `score = score
        # * 0.7`'nin tam sıralamasıyla birebir aynı.
        contributions: dict[str, float] = {}

        def scale_all(factor: float) -> None:
            for key in contributions:
                contributions[key] *= factor

        # Fear & Greed — contrarian yorum
        if context.fear_greed_index < 25:
            contributions["fear_greed"] = 2.0
            evidence.append(f"Aşırı korku tespit edildi ({context.fear_greed_index})")
            evidence.append("Kontraryan yorum: olası birikim bölgesi")
        elif context.fear_greed_index > 75:
            contributions["fear_greed"] = -2.0
            evidence.append(f"Aşırı açgözlülük tespit edildi ({context.fear_greed_index})")
            evidence.append("Kontraryan yorum: olası dağıtım bölgesi")
        elif context.fear_greed_index < 40:
            contributions["fear_greed"] = 0.5
            evidence.append(f"Korku yükselmiş ({context.fear_greed_index})")

        # Sosyal medya tonu
        if context.social_media_sentiment < -0.3:
            contributions["social_media"] = 1.0
            evidence.append("Sosyal medya duyarlılığı aşırı negatif — kontraryan sinyal")
        elif context.social_media_sentiment > 0.5:
            contributions["social_media"] = -0.5
            evidence.append("Sosyal medya öforik — dikkatli olunmalı")

        # Haber tonu
        if context.news_tone == "negative":
            contributions["news_tone"] = 0.3
            evidence.append("Negatif haber tonu, düşüş yönlü kalabalık pozisyonlanmaya işaret ediyor")
        elif context.news_tone == "positive":
            contributions["news_tone"] = -0.3
            evidence.append("Pozitif haber tonu — aşırı alım olabilir")

        # Google Trends
        if context.google_trends_score > 80:
            contributions["google_trends"] = -0.2
            evidence.append("Aşırı arama ilgisi, perakende yatırımcı aşırı ısınmasına işaret edebilir")
        elif context.google_trends_score < 20:
            contributions["google_trends"] = 0.2
            evidence.append("Düşük arama ilgisi — olası düşük değerleme")

        # Volatilite
        if context.volatility_index > 30:
            caveats.append(f"Yüksek volatilite ({context.volatility_index}) — pozisyon büyüklüğü kritik")
            scale_all(0.7)

        # Piyasa pozisyonlanması
        if context.positioning == "short_bias":
            contributions["positioning"] = 1.0
            evidence.append("Piyasa ağırlıklı short — sıkışma (squeeze) potansiyeli")
        elif context.positioning == "long_bias":
            contributions["positioning"] = -1.0
            evidence.append("Piyasa ağırlıklı long — düşüş riski")

        # Self-bias farkındalığı
        caveats.append("Sentiment sinyalleri refleksif ve kalabalığa bağımlıdır")

        score = sum(contributions.values())

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
            feature_contributions={k: round(v, 4) for k, v in contributions.items()},
        ).recalculate()
