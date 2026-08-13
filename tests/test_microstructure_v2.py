"""Order Flow ve Microstructure v2 testleri — Faz 394-418 (Cognitive Core 2.0)."""
from analytics.microstructure_v2 import compute_kyle_lambda


def _deterministic_trades(k: float, n: int = 25) -> list[dict]:
    """price_change[i] = k * signed_volume[i] ilişkisini BİREBİR sağlayan
    sentetik işlemler — gerçek regresyon eğiminin k'ya yakınsaması gerekir."""
    price = 100.0
    trades = [{"price": price, "quantity": 1.0, "side": "buy"}]
    for i in range(1, n):
        qty = 1.0 + (i % 5)
        side = "buy" if i % 2 == 0 else "sell"
        signed = qty if side == "buy" else -qty
        price = price + k * signed
        trades.append({"price": price, "quantity": qty, "side": side})
    return trades


def test_kyle_lambda_recovers_the_real_deterministic_relationship():
    trades = _deterministic_trades(k=0.05)
    result = compute_kyle_lambda(trades)
    assert result is not None
    assert abs(result["kyle_lambda"] - 0.05) < 1e-6
    assert result["sample_size"] == 25


def test_zero_price_impact_produces_near_zero_lambda():
    trades = _deterministic_trades(k=0.0)
    result = compute_kyle_lambda(trades)
    assert result is not None
    assert abs(result["kyle_lambda"]) < 1e-9


def test_below_min_sample_size_is_fail_closed():
    trades = _deterministic_trades(k=0.05, n=5)
    assert compute_kyle_lambda(trades) is None


def test_no_variance_in_signed_volume_is_fail_closed():
    # Her işlem AYNI büyüklükte ve AYNI yönde alış — işaretli hacimde
    # varyans yok, regresyon eğimi tanımsız.
    trades = [{"price": 100.0 + i * 0.01, "quantity": 1.0, "side": "buy"} for i in range(25)]
    assert compute_kyle_lambda(trades) is None


def test_kyle_lambda_pct_is_normalized_by_average_price():
    trades = _deterministic_trades(k=0.05)
    result = compute_kyle_lambda(trades)
    avg_price = sum(t["price"] for t in trades) / len(trades)
    assert abs(result["kyle_lambda_pct"] - (0.05 / avg_price)) < 1e-6
