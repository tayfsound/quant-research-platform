"""Yön Tahmini Baseline Karşılaştırması — Faz 442 (2026-09-07). Bkz.
/Users/emreturkes/.claude/plans/velvety-whistling-parasol.md.

Bağlam: GPT'nin önerisi — "Direction modelinin gerçekten bir şey öğrenip
öğrenmediğini görmek için Random/Always-LONG/Always-SHORT/Momentum/AI/
Council'i AYNI forward target üzerinde karşılaştır." Bugün elle
yapılan bu ölçüm (n≈6.900, gerçek 1sa ileri fiyat, `analytics/
forward_direction.py::label_forward_direction()`) çarpıcı bir sonuç
verdi: AI'nin nihai kararı (%43,8) random'ın (%49,9) ALTINDA. Bu modül
o ölçümü tekrarlanabilir, test edilmiş bir fonksiyona dönüştürüyor.

Kasıtlı olarak SADECE ölçüm/rapor — hiçbir canlı kararı etkilemiyor."""

MIN_SAMPLE_SIZE = 30
# "Random" ve eksik tahminler İÇİN deterministik %50 kullanılıyor — bir
# yazı-tura simülasyonunun BEKLENEN değeri zaten tam olarak 0.5, gerçek
# bir rastgele sayı üreteciyle simüle etmek (a) tekrarlanabilirliği
# bozar (b) hiçbir ek doğruluk katmaz.
COIN_FLIP_ACCURACY = 0.5


def _momentum_direction(market_regime: str | None) -> str | None:
    """market_regime (ör. 'bullish_normal'/'bearish_low') zaten HER
    karar için hesaplanan trend sınıflandırıcısından geliyor — yeni bir
    hesap değil, mevcut bir alanın momentum baseline'ı olarak yeniden
    kullanılması."""
    if not market_regime:
        return None
    if market_regime.startswith("bullish"):
        return "UP"
    if market_regime.startswith("bearish"):
        return "DOWN"
    return None


def compute_baseline_comparison(records: list[dict], threshold_pct: float = 0.0005) -> dict | None:
    """records: her biri {'entry_price', 'price_at_horizon', 'direction'
    (AI'nin nihai LONG/SHORT kararı), 'council_direction' (LONG/SHORT/
    None), 'market_regime'} olan GERÇEK kapanmış kararlar — `analytics.
    forward_direction.label_forward_direction()` ile aynı `entry_price`/
    `price_at_horizon` çiftinden üretiliyor.

    SADECE gerçek yön (UP/DOWN) hareket eden kayıtlar sayılıyor — NEUTRAL
    (fiyat anlamsız küçük bir hareket yapmış) kayıtlar hem ground-truth
    hem HER baseline için dışlanıyor (GPT'nin "gürültüye zorla etiket
    verme" uyarısıyla AYNI ilke). <MIN_SAMPLE_SIZE ikili (UP/DOWN)
    kayıtla fail-closed None — icat edilmiş bir doğruluk oranı asla
    üretilmez."""
    from analytics.forward_direction import label_forward_direction

    binary = []
    for r in records:
        gt = label_forward_direction(r.get("entry_price"), r.get("price_at_horizon"), threshold_pct)
        if gt in ("UP", "DOWN"):
            binary.append((r, gt))

    if len(binary) < MIN_SAMPLE_SIZE:
        return None

    n = len(binary)

    def _accuracy(predict_fn) -> float:
        correct = 0.0
        for r, gt in binary:
            pred = predict_fn(r)
            if pred is None:
                correct += COIN_FLIP_ACCURACY
            elif pred == gt:
                correct += 1.0
        return round(correct / n, 4)

    up_share = sum(1 for _, gt in binary if gt == "UP") / n

    return {
        "n": n,
        "up_share": round(up_share, 4),
        "accuracy": {
            "random": COIN_FLIP_ACCURACY,
            "always_long": _accuracy(lambda r: "UP"),
            "always_short": _accuracy(lambda r: "DOWN"),
            "momentum": _accuracy(lambda r: _momentum_direction(r.get("market_regime"))),
            "ai_final_direction": _accuracy(
                lambda r: "UP" if r.get("direction") == "LONG" else ("DOWN" if r.get("direction") == "SHORT" else None)
            ),
            "council_direction": _accuracy(
                lambda r: "UP" if r.get("council_direction") == "LONG"
                else ("DOWN" if r.get("council_direction") == "SHORT" else None)
            ),
        },
    }
