from risk.circuit_breakers.volatility import VolatilityCircuitBreaker


def test_volatility_circuit_breaker():
    cb = VolatilityCircuitBreaker(threshold=0.1, lookback=5)
    prices = [100, 110, 125, 145, 170, 200]
    for p in prices:
        result = cb.check(p)
    assert not result
    assert cb.tripped
