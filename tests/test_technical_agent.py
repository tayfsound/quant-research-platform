"""Technical Agent testleri."""
from agents.technical_agent import TechnicalAgent
from contracts.technical import TechnicalContext

def test_bullish_setup_generates_long():
    agent = TechnicalAgent()
    ctx = TechnicalContext(
        trend="bullish",
        momentum="strengthening",
        market_structure="higher_highs",
        volume_confirmation=True,
        ema_alignment="bullish_aligned",
    )
    opinion = agent.analyze(ctx)
    assert opinion.direction == "LONG"
    assert opinion.confidence > 0
    assert len(opinion.evidence) >= 2

def test_bearish_setup_generates_short():
    agent = TechnicalAgent()
    ctx = TechnicalContext(
        trend="bearish",
        momentum="weakening",
        market_structure="lower_lows",
        rsi_value=80.0,
    )
    opinion = agent.analyze(ctx)
    assert opinion.direction == "SHORT"
    assert opinion.confidence > 0

def test_ranging_market_waits():
    agent = TechnicalAgent()
    ctx = TechnicalContext(
        trend="neutral",
        momentum="neutral",
        market_structure="ranging",
    )
    opinion = agent.analyze(ctx)
    assert opinion.direction == "WAIT"

def test_volume_divergence_warning():
    agent = TechnicalAgent()
    ctx = TechnicalContext(
        trend="bullish",
        momentum="strengthening",
        market_structure="higher_highs",
        volume_confirmation=False,
    )
    opinion = agent.analyze(ctx)
    assert any("Volume not confirming" in c for c in opinion.caveats)
