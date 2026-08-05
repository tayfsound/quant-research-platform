"""Order Flow Agent testleri."""
from agents.order_flow_agent import OrderFlowAgent
from contracts.order_flow import OrderFlowContext


def test_bid_heavy_imbalance_generates_long():
    agent = OrderFlowAgent()
    ctx = OrderFlowContext(bid_ask_imbalance=0.5, aggressive_buy_ratio=0.7, spread_bps=2.0)
    opinion = agent.analyze(ctx)
    assert opinion.direction == "LONG"
    assert opinion.confidence > 0


def test_ask_heavy_imbalance_generates_short():
    agent = OrderFlowAgent()
    ctx = OrderFlowContext(bid_ask_imbalance=-0.5, aggressive_buy_ratio=0.3, spread_bps=2.0)
    opinion = agent.analyze(ctx)
    assert opinion.direction == "SHORT"


def test_wide_spread_dampens_confidence_and_warns():
    agent = OrderFlowAgent()
    tight = agent.analyze(OrderFlowContext(bid_ask_imbalance=0.5, spread_bps=2.0))
    wide = agent.analyze(OrderFlowContext(bid_ask_imbalance=0.5, spread_bps=25.0))
    assert wide.confidence < tight.confidence
    assert any("wide spread" in c.lower() for c in wide.caveats)


def test_balanced_book_waits():
    agent = OrderFlowAgent()
    opinion = agent.analyze(OrderFlowContext())
    assert opinion.direction == "WAIT"
