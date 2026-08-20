"""Quant Agent — istatistiksel/kantitatif sinyal uzmanı."""
from contracts.agent import AgentDomain, AgentOpinion
from contracts.quant import QuantContext

# Faz 317-sonrası — kullanıcı bulgusu (2026-08-20): "Quant ajanın isabeti
# sıfıra indi." Gerçek geçmiş veriyle ölçüldü (1333 kapanmış işlem,
# feature_ic.py metodolojisiyle): bu ajanın nihai yönü long_term_trend_
# regime (200-EMA tabanlı, YAVAŞ/gecikmeli) ile AYNI taraftaysa
# ("agree" — ör. LONG + bull_trend) kazanma oranı SADECE %27.9 (n=308,
# ortalama getiri -%3.94) — yazı turadan kötü. TERS taraftaysa
# ("disagree") %71.4 (n=7) — ama bu örneklem (7) istatistiksel olarak
# GÜVENİLMEZ, kalıcı bir "tersine çevir" kararı için yetersiz. Bu yüzden
# SADECE "agree" durumunda confidence indiriliyor (gerçek, sağlam
# kanıtlı n=308) — "disagree" durumunda HİÇBİR ayarlama yapılmıyor
# (yetersiz kanıt, kalıcı ters çevirme riskli olurdu — piyasa tekrar
# gerçek mean-reverting bir rejime dönerse bu ajanın Z-score mantığı
# muhtemelen yeniden işe yarar, kör bir kalıcı inversiyon o zaman bizi
# YANLIŞ tarafta bırakırdı). Yön ASLA değişmiyor, SADECE confidence.
_TREND_AGREEMENT_CONFIDENCE_DISCOUNT = 0.6


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

        # Faz 222: gerçek 200 EMA'ya göre uzun-vade rejim — Hurst'ün ölçtüğü
        # kısa-vadeli istatistiksel karakterden (trending mi mean-reverting mi)
        # bağımsız, ayrı bir kanıt: fiyat gerçekten uzun vadede yükseliş/düşüş
        # trendinde mi. candle_lookback yeterince derinse (>=220 bar) hesaplanır.
        if context.long_term_trend_regime == "bull_trend":
            contributions["long_term_trend_regime"] = 1.0
            evidence.append("Uzun vadeli rejim (gerçek 200-EMA, 220+ mum geriye bakış): yükseliş trendi")
        elif context.long_term_trend_regime == "bear_trend":
            contributions["long_term_trend_regime"] = -1.0
            evidence.append("Uzun vadeli rejim (gerçek 200-EMA, 220+ mum geriye bakış): düşüş trendi")
        elif context.long_term_trend_regime == "insufficient_data":
            caveats.append("Uzun vadeli trend rejimi hesaplanamıyor — candle_lookback < 220 mum")

        # Faz 268-sonrası — gerçek olay (2026-08-12): bu YAVAŞ/gecikmeli
        # sinyal, fiyat aktif olarak tersine dönerken bile eski rejimi
        # okumaya devam edip 50 ardışık gerçek kayba katkıda bulundu
        # (agents/technical_agent.py de aynı yönde yanılmıştı — bu tek
        # başına bir "council'i geçersiz kılan" bug değildi, ama bu
        # SPESİFİK sinyalin gerçek geçmişte gösterdiği bir zaafiyet).
        # Gerçek bir istatistiksel changepoint testi (market_data/
        # features/signal_engine.py::_regime_changepoint) son dönem
        # getirisinin bu rejimin yönüne ters, anlamlı bir kayma
        # gösterdiğini tespit ederse, SADECE bu sinyalin katkısı
        # (Hurst/z-score tabanlı diğer kanıtlar değil) indirime uğruyor.
        if context.regime_changepoint_detected and contributions.get("long_term_trend_regime", 0.0) != 0.0:
            caveats.append(
                "Rejim değişim noktası (changepoint) tespit edildi — son dönem getirileri bu "
                "(gecikmeli) uzun vadeli rejimden istatistiksel olarak anlamlı şekilde ayrışıyor"
            )
            contributions["long_term_trend_regime"] *= 0.3

        # Aşırı volatilite — güveni azalt
        if context.realized_vol_percentile > 90:
            caveats.append(f"Gerçekleşen volatilite {context.realized_vol_percentile:.0f}. persentilde — istatistiksel güvenilirlik azaldı")
            scale_all(0.6)

        # Faz 268e — gerçek bulgu: Hurst ölü bölgesindeyken (0.45-0.55, "ne
        # trend ne mean-reversion") bu belirsizlik SADECE bir caveat olarak
        # not ediliyordu, skoru hiç etkilemiyordu — ajan aynı anda "kısa/
        # orta vadeli istatistiksel karakterden emin değilim" diyip tek
        # başına zayıf bir uzun-vade sinyaliyle (long_term_trend_regime)
        # yüksek görünen bir skor üretebiliyordu (canlıda doğrulandı: SI=F/
        # GC=F/XAUTUSDT'de tekrar eden yanlış SHORT'lar — TEK kanıt "200-
        # EMA bear trend", Hurst 0.47 ölü bölgede, yine de skor tam
        # kullanılıyordu). Aşırı volatilite indirimiyle AYNI desen —
        # istatistiksel zeminin belirsiz olduğu bir durumda güven de
        # buna göre indirilmeli.
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

        # Faz 317-sonrası — bkz. _TREND_AGREEMENT_CONFIDENCE_DISCOUNT
        # üstündeki yorum. SADECE "agree" durumunda (gerçek, n=308 kanıt)
        # indiriliyor — direction ASLA değişmiyor.
        if direction in ("LONG", "SHORT") and context.long_term_trend_regime in ("bull_trend", "bear_trend"):
            agent_side = "bull_trend" if direction == "LONG" else "bear_trend"
            if context.long_term_trend_regime == agent_side:
                confidence *= _TREND_AGREEMENT_CONFIDENCE_DISCOUNT
                caveats.append(
                    f"Yön, uzun vadeli rejimle ({context.long_term_trend_regime}) AYNI tarafta — "
                    "geçmiş veride bu durum daha düşük isabetle ilişkili (n=308, %27.9 kazanma), "
                    "confidence indirildi"
                )

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
