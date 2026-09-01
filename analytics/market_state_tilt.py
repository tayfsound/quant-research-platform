"""Market State Confidence Eğimi — Faz 402 (Market State Katmanı Faz 2).

`analytics/moe_regime_router.py`'nin (Faz 353, canlıda kanıtlanmış: 4410
kapalı kararla doğrulanmış, MAX_TILT=%30, hiçbir uzmanı asla tamamen
susturmayan) AYNI şablonu — bu sefer Hurst-tabanlı trend/mean-reversion
ekseni yerine, `market_data.features.market_state_engine::compute_market_
state()`'in `reversing` sinyalini kullanıyor.

Kasıtlı olarak SADECE öneri (saf fonksiyon, ajan ağırlığını burada
DEĞİŞTİRMİYOR) — canlıya bağlanması `services/council_orchestrator.py`'de
AYRI, `market_state_tilt_enabled` ayarıyla (varsayılan kapalı) korunan
bir karar."""

MAX_TILT = 0.3  # moe_regime_router.py ile AYNI sınır — asla bir ajanı tamamen susturmaz


def compute_market_state_tilt(market_state: dict) -> dict:
    """market_state: compute_market_state()'in çıktısı. Döner:
    {agreeing_weight, opposing_weight, direction} — ağırlıklar [1-MAX_TILT,
    1+MAX_TILT] aralığında, MEVCUT performance_weight'i ÇARPMAK için
    tasarlanmış çarpanlar (yerine geçmek için değil). SADECE `reversing=
    True` VE yönlü (LONG/SHORT) bir direction varken tetiklenir — sideways-
    market kapısının öğrettiği ders: tek başına geniş kullanılan yumuşak
    bir sinyal çok fazla yanlış pozitif üretir, dar+bileşik güvenli.
    Tetiklenmezse no-op (1.0/1.0/None)."""
    direction = market_state.get("direction")
    if not market_state.get("reversing") or direction not in ("LONG", "SHORT"):
        return {"agreeing_weight": 1.0, "opposing_weight": 1.0, "direction": None}

    confidence = min(max(market_state.get("confidence", 0.0), 0.0), 1.0)
    tilt = confidence * MAX_TILT
    return {
        "agreeing_weight": round(1.0 + tilt, 4),
        "opposing_weight": round(1.0 - tilt, 4),
        "direction": direction,
    }
