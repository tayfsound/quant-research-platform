from risk.limits.enforcement import RiskEnforcer, RiskLimit
from risk.circuit_breakers.volatility import VolatilityCircuitBreaker

def test_position_size_limit():
    enforcer = RiskEnforcer(RiskLimit(max_position_size=0.5))
    ok, reason = enforcer.check_position(0.6, 10000)
    assert not ok
    assert reason == "POSITION_SIZE_EXCEEDED"

def test_drawdown_limit():
    enforcer = RiskEnforcer(RiskLimit(max_drawdown_pct=0.05))
    enforcer.peak_equity = 10000
    ok, reason = enforcer.check_position(0.1, 9400)
    assert not ok
    assert reason == "DRAWDOWN_LIMIT"

def test_daily_loss_limit():
    enforcer = RiskEnforcer(RiskLimit(daily_loss_limit=100))
    enforcer.check_daily_loss(-50)
    enforcer.check_daily_loss(-60)
    ok, reason = enforcer.check_daily_loss(0)
    assert not ok
    assert reason == "DAILY_LOSS_LIMIT"

def test_volatility_circuit_breaker():
    cb = VolatilityCircuitBreaker(threshold=0.1, lookback=5)
    prices = [100, 110, 125, 145, 170, 200]
    for p in prices:
        result = cb.check(p)
    assert not result
    assert cb.tripped
