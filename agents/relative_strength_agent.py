"""Relative Strength Agent — Faz 242-243: 10. oy-veren ajan.

Fikir: bir sembolün MUTLAK getirisi (yükseldi/düştü) tek başına zayıf bir
sinyal — bütün piyasa yükseliyorsa herkes yükselir. Bu ajan onun yerine
GÖRELİ soruyu soruyor: bu sembol, aynı anda izlenen havuza göre daha mı
güçlü/zayıf performans gösteriyor? Güçlü/zayıf kalan bir sembolün bu
eğilimi kısa vadede devam ettirmesi (momentum/relative strength) klasik,
iyi belgelenmiş bir gözlem — ama tek bir ölçümle bile YANLIŞ yöne
çekilebileceği için (basket_size < 3) istatistiksel olarak anlamsız kabul
edilip dürüstçe WAIT deniyor.

Faz 268-sonrası — kullanıcı bulgusu: havuz eskiden SADECE ~49 sembollük
watchlist'ti (1 saatlik pencere) — kripto piyasası yüksek korelasyonlu
olduğu için neredeyse hiçbir zaman anlamlı ayrışma bulunamıyordu. Artık
services/context_adapter.py::to_relative_strength() TÜM Binance Futures
USDT-marjinli sembollerinin (yüzlerce) GERÇEK 24 saatlik getirisini
kullanıyor (bkz. services/market_breadth.py) — eşikler bu daha geniş
pencereye göre yeniden kalibre edildi (24h getiriler 1h'den doğal olarak
çok daha büyük ölçekli)."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.relative_strength import RelativeStrengthContext

MIN_BASKET_SIZE = 3
# Faz 268-sonrası: 1 saatlik pencereden (%1) 24 saatlik pencereye (%3)
# yeniden kalibre edildi — 24h kripto getirileri doğal olarak çok daha
# geniş ölçekli, eski %1 eşiği artık neredeyse HER zaman tetiklenirdi.
# Gerçek veri birikince (kapanmış işlem sonuçlarıyla) yeniden ölçülmeli.
DIVERGENCE_THRESHOLD_PCT = 0.03
# Faz 268-sonrası: %6'dan %15'e yeniden kalibre edildi (24h ölçeğine
# uyacak şekilde) — aynı gerekçe: max confidence'a (0.85) artık gerçekten
# aşırı bir ayrışmada ulaşılsın, sıradan günlük oynaklıkta değil.
CONFIDENCE_DIVISOR_PCT = 0.15


class RelativeStrengthAgent:
    def __init__(self):
        self.agent_id = "relative_strength_agent_v1"

    def analyze(self, context: RelativeStrengthContext) -> AgentOpinion:
        evidence = []
        caveats = []

        if context.basket_size < MIN_BASKET_SIZE:
            caveats.append(
                f"Karşılaştırma için yeterli piyasa verisi yok "
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
                f"Piyasa geneli (24s) ortalamasının {rs:.2%} üzerinde performans "
                f"(kendi 24s getirisi: {context.symbol_return_pct:.2%}, "
                f"piyasa ortalaması: {context.basket_mean_return_pct:.2%}, "
                f"{context.basket_size} sembol)"
            )
        elif rs < -DIVERGENCE_THRESHOLD_PCT:
            direction = "SHORT"
            evidence.append(
                f"Piyasa geneli (24s) ortalamasının {abs(rs):.2%} altında performans "
                f"(kendi 24s getirisi: {context.symbol_return_pct:.2%}, "
                f"piyasa ortalaması: {context.basket_mean_return_pct:.2%}, "
                f"{context.basket_size} sembol)"
            )
        else:
            direction = "WAIT"
            caveats.append(
                f"Piyasa geneli (24s) ortalamasından belirgin bir ayrışma yok ({rs:.2%})"
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
