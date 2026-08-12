"""Relative Strength Agent — Faz 242-243: 10. oy-veren ajan.

Fikir: bir sembolün MUTLAK getirisi (yükseldi/düştü) tek başına zayıf bir
sinyal — bütün piyasa yükseliyorsa herkes yükselir. Bu ajan onun yerine
GÖRELİ soruyu soruyor: bu sembol, aynı anda izlenen DİĞER watchlist
sembollerine göre daha mı güçlü/zayıf performans gösteriyor? Watchlist
genelinde güçlü/zayıf kalan bir sembolün bu eğilimi kısa vadede devam
ettirmesi (momentum/relative strength) klasik, iyi belgelenmiş bir
gözlem — ama tek bir ölçümle bile YANLIŞ yöne çekilebileceği için
(basket_size < 3) istatistiksel olarak anlamsız kabul edilip dürüstçe
WAIT deniyor."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.relative_strength import RelativeStrengthContext

MIN_BASKET_SIZE = 3
# Faz 242-243: %1'in altındaki bir fark, watchlist'in kendi normal
# gürültüsü içinde kaybolur — gerçek bir "göreli güç/zayıflık" iddiası
# için daha belirgin bir ayrışma gerekiyor.
DIVERGENCE_THRESHOLD_PCT = 0.01
# %6'lık bir göreli sapma, bu ajanın kendi ölçeğinde "çok güçlü" kabul
# edilip max confidence'a (0.85, diğer ajanlarla aynı tavan) yaklaşır.
CONFIDENCE_DIVISOR_PCT = 0.06


class RelativeStrengthAgent:
    def __init__(self):
        self.agent_id = "relative_strength_agent_v1"

    def analyze(self, context: RelativeStrengthContext) -> AgentOpinion:
        evidence = []
        caveats = []

        if context.basket_size < MIN_BASKET_SIZE:
            caveats.append(
                f"Karşılaştırma için yeterli watchlist verisi yok "
                f"({context.basket_size}/{MIN_BASKET_SIZE} sembol) — göreli güç ölçülemiyor"
            )
            return AgentOpinion(
                agent_id=self.agent_id,
                domain=AgentDomain.RELATIVE_STRENGTH,
                direction="WAIT",
                confidence=0.0,
                evidence_strength=0.70,
                data_quality=0.60,
                freshness=0.90,
                source_reliability=0.65,
                evidence=evidence,
                caveats=caveats,
            ).recalculate()

        rs = context.relative_strength_pct

        if rs > DIVERGENCE_THRESHOLD_PCT:
            direction = "LONG"
            evidence.append(
                f"Watchlist ortalamasının {rs:.2%} üzerinde performans "
                f"(kendi getiri: {context.symbol_return_pct:.2%}, "
                f"havuz ortalaması: {context.basket_mean_return_pct:.2%}, "
                f"{context.basket_size} sembol)"
            )
        elif rs < -DIVERGENCE_THRESHOLD_PCT:
            direction = "SHORT"
            evidence.append(
                f"Watchlist ortalamasının {abs(rs):.2%} altında performans "
                f"(kendi getiri: {context.symbol_return_pct:.2%}, "
                f"havuz ortalaması: {context.basket_mean_return_pct:.2%}, "
                f"{context.basket_size} sembol)"
            )
        else:
            direction = "WAIT"
            caveats.append(
                f"Watchlist ortalamasından belirgin bir ayrışma yok ({rs:.2%})"
            )

        confidence = min(abs(rs) / CONFIDENCE_DIVISOR_PCT, 0.85)

        return AgentOpinion(
            agent_id=self.agent_id,
            domain=AgentDomain.RELATIVE_STRENGTH,
            direction=direction,
            confidence=round(confidence, 3),
            evidence_strength=0.70,
            data_quality=0.75,
            freshness=0.90,
            source_reliability=0.65,
            evidence=evidence,
            caveats=caveats,
        ).recalculate()
