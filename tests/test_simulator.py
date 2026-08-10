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


def test_fill_engine_applies_adverse_slippage_in_the_correct_direction_for_long_and_short():
    """Faz 268e: kritik bulgu — services/orchestrator.py (tek gerçek
    çağıran) her zaman "LONG"/"SHORT" gönderiyor, SlippageModel ise sadece
    "BUY"/"SELL" biliyor. Bu eşleme yoksa (önceki hal) "LONG" hiçbir zaman
    "BUY"'a eşit olmadığından apply() her zaman else dalına (price - slip)
    düşüyordu — LONG pozisyonlar gerçekte olması gerekenden sistematik
    olarak daha İYİ (düşük) bir giriş fiyatıyla açılıyordu. Gerçek bir
    alışta olumsuz kayma fiyatı YÜKSELTMELİ (LONG -> BUY), gerçek bir
    satışta DÜŞÜRMELİ (SHORT -> SELL)."""
    engine = FillEngine()
    long_result = engine.simulate({"direction": "LONG", "size": 1.0}, 50000)
    short_result = engine.simulate({"direction": "SHORT", "size": 1.0}, 50000)
    assert long_result.filled_price > 50000
    assert short_result.filled_price < 50000
