"""Strategy × Regime Gate — Faz 366, saf (pure) hesaplama katmanı.

analytics/pyramid_regime_gate.py'nin AYNI ilkesi (bir bulgu insan
onayından geçtikten sonra, canlı girişi engelleyen basit bir üyelik
kontrolü) ama tek bir sabit yerine ÇOĞUL, veri kaynaklı bir onaylı-çift
kümesi — strategy_hypothesis_scanner.py'nin ürettiği, insan onayından
geçmiş HER (strateji, rejim) adayı buraya eklenebilir, kod değişikliği
gerekmeden."""


def is_strategy_regime_gated(
    strategy: str,
    market_regime: str | None,
    blocked_pairs: set[tuple[str, str]],
) -> bool:
    """True dönerse bu (strateji, rejim) kombinasyonu insan onaylı bir
    bulguya göre engellenmeli. market_regime None/bilinmiyorsa (fail-
    closed DEĞİL burada — pyramid_regime_gate'in aksine bu kapı SADECE
    doğrulanmış YÜKSEK GÜVEN adayları için var, bilinmeyen rejimde
    genel bir yasak koymuyor) hiçbir çiftle eşleşmez, False döner."""
    if market_regime is None:
        return False
    return (strategy, market_regime) in blocked_pairs
