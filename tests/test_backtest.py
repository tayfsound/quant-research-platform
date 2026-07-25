"""Backtest testleri."""
from datetime import datetime, timedelta


def test_historical_replay():
    from backtest.historical_replay.engine import HistoricalReplay
    data = [
        {"timestamp": datetime.now(), "close": 50000.0},
        {"timestamp": datetime.now() + timedelta(hours=1), "close": 51000.0},
    ]
    results = []
    def on_candle(c):
        results.append(c)
        return None
    engine = HistoricalReplay(data)
    engine.run(on_candle)
    assert len(results) == 2

def test_monte_carlo():
    from backtest.monte_carlo.simulator import MonteCarloSimulator
    returns = [0.001, -0.002, 0.003, 0.0, -0.001] * 20
    sim = MonteCarloSimulator(returns, num_simulations=100, horizon=10)
    result = sim.run()
    assert "var_95" in result
    assert "expected_final" in result

def test_walk_forward():
    from backtest.walk_forward.validator import WalkForwardValidator
    data = [{"close": i} for i in range(300)]
    validator = WalkForwardValidator(train_window=180, test_window=30, embargo=2)
    splits = validator.split(data)
    assert len(splits) >= 2
