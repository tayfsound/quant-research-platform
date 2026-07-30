"""Simulator testleri."""
from simulator.fee_engine import FeeEngine, FeeConfig
from simulator.slippage_model import SlippageModel
from simulator.fill_engine import FillEngine

def test_fee_calculation():
    fee = FeeEngine(FeeConfig(maker_rate=0.0002, taker_rate=0.0005))
    assert fee.calculate(100000, is_maker=False) == 50.0

def test_slippage_direction():
    slippage = SlippageModel(base_bps=10.0)
    buy = slippage.apply(50000, "BUY", 1.0)
    sell = slippage.apply(50000, "SELL", 1.0)
    assert buy > 50000
    assert sell < 50000

def test_fill_engine_neutral():
    engine = FillEngine()
    result = engine.simulate({"direction": "NEUTRAL"}, 50000)
    assert result.fee == 0.0
