"""Faz 244-246: CPPI (Constant Proportion Portfolio Insurance) — Monte
Carlo'nun tahmin ettiği "yakın vadeli seri kayıp" riskine göre dinamik
exposure küçültme.

Klasik CPPI, exposure = multiplier * (portfolio_value - floor) formülüyle
sabit bir "koruma tabanı" üstündeki miktarı riske atar. Burada floor,
gerçek portföy değeri yerine simulate_regime_drawdown_risk()'in tahmin
ettiği ruin-eşiği aşma OLASILIĞINA göre ifade ediliyor — MetaStage'in
(Kelly) zaten belirlediği final_size'ı EK bir kesirle küçültüyor, asla
büyütmüyor (bu oturum boyunca tekrarlanan ilke: AI kendi risk tavanını
genişletemez, sadece daraltabilir)."""

# breach_probability bu eşiği geçmeden hiçbir küçültme uygulanmaz.
BREACH_PROBABILITY_THRESHOLD = 0.05
# En agresif küçültmede bile çarpan bu tabanın altına inmez — pozisyonu
# TAMAMEN iptal etme kararı bu modülün işi değil, RiskGateStage'in
# statik limitleri zaten o rolü üstleniyor.
MIN_EXPOSURE_MULTIPLIER = 0.25


def cppi_exposure_multiplier(monte_carlo_result: dict) -> float:
    """breach_probability None ise (yetersiz rejim verisi — fail-closed)
    çarpan 1.0, mevcut (Kelly'nin belirlediği) boyut hiç değişmez. Eşiği
    aşan her fazladan olasılık noktası, çarpanı [MIN_EXPOSURE_MULTIPLIER,
    1.0] aralığında DOĞRUSAL olarak küçültür — icat edilmiş bir eğri
    değil, en basit/açıklanabilir orantı."""
    breach_probability = monte_carlo_result.get("breach_probability")
    if breach_probability is None:
        return 1.0
    if breach_probability <= BREACH_PROBABILITY_THRESHOLD:
        return 1.0

    excess = (breach_probability - BREACH_PROBABILITY_THRESHOLD) / (1.0 - BREACH_PROBABILITY_THRESHOLD)
    multiplier = 1.0 - excess * (1.0 - MIN_EXPOSURE_MULTIPLIER)
    return max(MIN_EXPOSURE_MULTIPLIER, min(multiplier, 1.0))
