"""Simülatör doğrulama testleri."""
from simulator.execution import ExecutionEngine, Order, OrderSide, OrderType


def test_market_order_fills():
    engine = ExecutionEngine()
    engine.order_book.update(bid=50000.0, ask=50001.0, bid_size=10.0, ask_size=10.0)
    order = Order(symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1.0)
    fill = engine.execute(order)
    assert fill.quantity == 1.0
    assert fill.price > 0
    assert fill.fee > 0

def test_fee_calculation():
    from simulator.fee_engine.calculator import FeeEngine
    engine = FeeEngine()
    fee = engine.calculate(notional=10000.0, is_maker=True)
    assert fee == 2.0  # 10000 * 0.0002

def test_liquidation():
    from simulator.liquidation_engine.engine import LiquidationEngine
    from simulator.margin import MarginAccount
    account = MarginAccount(balance=1000.0)
    account.open_position("BTCUSDT", "long", quantity=0.1, price=50000.0, leverage=10.0)
    # Margin: 0.1*50000/10 = 500. Balance: 500.
    engine = LiquidationEngine()
    liquidated = engine.check(account, {"BTCUSDT": 45000.0})  # -%10 düşüş
    assert len(liquidated) > 0
