from backtest.walk_forward import WalkForwardEngine
from backtest.stress_scenarios import StressEngine

def test_walk_forward_runs():
    prices = list(range(100, 500))
    engine = WalkForwardEngine(train_size=100, test_size=50, step=50)
    results = engine.run(prices, lambda p: 1 if p[-1] > p[0] else -1)
    assert len(results) >= 1

def test_stress_scenarios():
    prices = [100.0] * 20
    engine = StressEngine()
    results = engine.run_all(prices)
    assert "flash_crash" in results
