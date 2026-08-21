"""Quant Agent — istatistiksel/kantitatif sinyal uzmanı."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.quant import QuantContext

# Faz 339 — gerçek bulgu (kullanıcı bulgusu: "quant ajanın son 20
# tahmininde isabet %0-5"). Faz 317'nin confidence-indirim bandaid'i
# yetmedi — kök nedene inildi: son 3000 kapanmış kararda quant'ın 489
# LONG/SHORT oyu, TEK kanıt kaynağına göre ikiye ayrıldı. long_term_
# trend_regime (yavaş/gecikmeli 200-EMA) TEK BAŞINA ateşlendiğinde
# (oyların %65'i, n=319): %15.7 isabet — yazı turadan kötü. Gerçek
# Hurst/z-score/otokorelasyon sinyali ateşlendiğinde (n=17): %76.5 —
# küçük örneklem ama %50 şansla açıklanamayacak kadar iyi. Sonuç:
# long_term_trend_regime bu ajanın kimliğine (Hurst'ün ölçtüğü KISA
# VADELİ istatistiksel karakter) hiç ait değildi, zaten Faz 222'de
# "ayrı, bağımsız bir kanıt" olarak eklenmişti — ve tam olarak batıran
# kısımdı. İndirmek yetmedi, TAMAMEN kaldırıldı — ajan artık SADECE
# kendi gerçek istatistiksel çekirdeğine (Hurst rejimi + z-score
# mean-reversion + otokorelasyon momentum) dayanıyor, çok daha seyrek
# ama gerçek kenarlı oy veriyor.


class QuantAgent:
    def __init__(self):
        self.agent_id = "quant_agent_v1"

    def analyze(self, context: QuantContext) -> AgentOpinion:
        evidence = []
        caveats = []
        # Faz 268-sonrası: Feature Importance — SHAP gibi bir YAKLAŞIK
        # yöntem değil, bu skorlama zaten kesin/katkısal bir fonksiyon.
        # Her isimli sinyalin score'a GERÇEK sayısal katkısı burada
        # tutuluyor; çarpımsal indirimler (volatilite, Hurst ölü bölge)
        # TÜM katkılara aynı oranda uygulanıyor ki toplam her zaman
        # gerçek score'a eşit kalsın.
        contributions: dict[str, float] = {}

        def scale_all(factor: float) -> None:
            for key in contributions:
                contributions[key] *= factor

        # Hurst exponent rejimi belirler: <0.5 mean-reverting, >0.5 trending
        mean_reverting_regime = context.hurst_exponent < 0.45
        trending_regime = context.hurst_exponent > 0.55
        hurst_dead_zone = False

        if mean_reverting_regime:
            evidence.append(f"Hurst exponent {context.hurst_exponent:.2f} — ortalamaya dönüş (mean-reverting) rejimi")
            # Mean-reversion rejiminde z-score'un TERSİNE bahis
            if context.zscore <= -2.0:
                contributions["zscore_mean_reversion"] = 2.0
                evidence.append(f"Z-score {context.zscore:.2f} — istatistiksel olarak aşırı satım")
            elif context.zscore >= 2.0:
                contributions["zscore_mean_reversion"] = -2.0
                evidence.append(f"Z-score {context.zscore:.2f} — istatistiksel olarak aşırı alım")
        elif trending_regime:
            evidence.append(f"Hurst exponent {context.hurst_exponent:.2f} — trend rejimi")
            # Trend rejiminde otokorelasyonun YÖNÜNDE bahis (momentum devam eder varsayımı)
            if context.autocorrelation > 0.3:
                contributions["autocorrelation_momentum"] = 1.5
                evidence.append(f"Pozitif otokorelasyon {context.autocorrelation:.2f} — momentum devam ediyor")
            elif context.autocorrelation < -0.3:
                contributions["autocorrelation_momentum"] = -1.5
                evidence.append(f"Negatif otokorelasyon {context.autocorrelation:.2f} — momentum devam ediyor")
        else:
            caveats.append(f"Hurst exponent {context.hurst_exponent:.2f} — rastgele yürüyüşe yakın, istatistiksel avantaj yok")
            hurst_dead_zone = True

        # Aşırı volatilite — güveni azalt
        if context.realized_vol_percentile > 90:
            caveats.append(f"Gerçekleşen volatilite {context.realized_vol_percentile:.0f}. persentilde — istatistiksel güvenilirlik azaldı")
            scale_all(0.6)

        if hurst_dead_zone:
            scale_all(0.5)

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
            domain=AgentDomain.QUANT,
            direction=direction,
            confidence=round(confidence, 3),
            evidence_strength=0.75,
            data_quality=0.85,
            freshness=0.9,
            source_reliability=0.8,
            evidence=evidence,
            caveats=caveats,
            feature_contributions={k: round(v, 4) for k, v in contributions.items()},
        ).recalculate()
