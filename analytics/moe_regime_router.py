"""Momentum/Mean-Reversion Mixture-of-Experts Router — Faz 369-393
(Cognitive Core 2.0).

hurst_exponent (market_data/features/signal_engine.py::compute_quant_
signals) GERÇEK bir piyasa karakteri sinyali: >0.5 trend-takipçi
(momentum) davranışının, <0.5 mean-reversion davranışının istatistiksel
olarak baskın olduğu bir rejimi işaret ediyor. Şu ana kadar bu bilgi
hesaplanıyor ama HİÇBİR ajanın konviksiyonunu ayarlamak için
kullanılmıyordu — technical_agent'ın momentum/trend sinyali ile
quant_agent'ın zscore (mean-reversion) sinyali her zaman EŞİT ağırlıkla
değerlendiriliyordu, piyasanın o anki istatistiksel karakterinden
bağımsız olarak.

Bu modül, hurst_exponent'e göre "momentum-flavored" ve "mean-reversion-
flavored" sinyallere verilecek göreli ağırlığı öneriyor — klasik,
literatürde tanımlı bir mixture-of-experts routing ilkesi (rejime göre
uzman seç), icat edilmiş bir formül değil.

Kasıtlı olarak SADECE öneri — hiçbir ajanın gerçek confidence'ını burada
otomatik DEĞİŞTİRMİYOR, mevcut oy konseyine WIRE edilmemiş. Yeni bir
mekanizmanın canlıya alınması ayrı, gerçek OOS doğrulama + insan onayı
gerektiren bir karar (proje kuralı: 'yeni karmaşıklık kendi edge'ini
kanıtlamalı')."""

HURST_TRENDING_THRESHOLD = 0.55
HURST_MEAN_REVERTING_THRESHOLD = 0.45
MAX_TILT = 0.3  # en fazla %30 ağırlık kayması — asla bir uzmanı tamamen susturmaz


def compute_moe_expert_weights(hurst_exponent: float) -> dict:
    """hurst_exponent: signal_engine.compute_quant_signals'ın ürettiği
    GERÇEK Hurst üsteli ([0, 1] aralığında beklenir). Döner:
    {momentum_weight, mean_reversion_weight, regime} — ağırlıklar
    [1-MAX_TILT, 1+MAX_TILT] aralığında, mevcut confidence'ı ÇARPMAK
    için tasarlanmış çarpanlar (yerine geçmek için değil)."""
    if hurst_exponent >= HURST_TRENDING_THRESHOLD:
        excess = min((hurst_exponent - HURST_TRENDING_THRESHOLD) / (1.0 - HURST_TRENDING_THRESHOLD), 1.0)
        tilt = excess * MAX_TILT
        return {
            "momentum_weight": round(1.0 + tilt, 4),
            "mean_reversion_weight": round(1.0 - tilt, 4),
            "regime": "trending",
        }
    if hurst_exponent <= HURST_MEAN_REVERTING_THRESHOLD:
        excess = min((HURST_MEAN_REVERTING_THRESHOLD - hurst_exponent) / HURST_MEAN_REVERTING_THRESHOLD, 1.0)
        tilt = excess * MAX_TILT
        return {
            "momentum_weight": round(1.0 - tilt, 4),
            "mean_reversion_weight": round(1.0 + tilt, 4),
            "regime": "mean_reverting",
        }
    return {"momentum_weight": 1.0, "mean_reversion_weight": 1.0, "regime": "neutral"}
