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


def test_confirming_tradingview_signal_adds_evidence_not_a_new_direction():
    """Faz 193: TradingView ikinci görüş — kendi hesapladığı yönü teyit
    ederse evidence'a eklenir, yönü DEĞİŞTİRMEZ."""
    agent = TechnicalAgent()
    ctx = TechnicalContext(
        trend="bullish", momentum="strengthening", market_structure="higher_highs",
        external_signal="bullish", external_signal_source="tradingview",
    )
    opinion = agent.analyze(ctx)
    assert opinion.direction == "LONG"
    assert any("TradingView" in e for e in opinion.evidence)


def test_conflicting_tradingview_signal_adds_caveat_not_a_direction_flip():
    """TradingView kendi iç görüşle çelişirse sadece bir uyarı (caveat)
    eklenir — tek başına yönü LONG'dan SHORT'a çevirmez."""
    agent = TechnicalAgent()
    ctx = TechnicalContext(
        trend="bullish", momentum="strengthening", market_structure="higher_highs",
        external_signal="bearish", external_signal_source="tradingview",
    )
    opinion = agent.analyze(ctx)
    assert opinion.direction == "LONG"  # kendi iç görüşü hâlâ geçerli
    assert any("çelişiyor" in c for c in opinion.caveats)


def test_no_external_signal_means_no_extra_evidence_or_caveat():
    agent = TechnicalAgent()
    ctx = TechnicalContext(trend="bullish", momentum="strengthening", market_structure="higher_highs")
    opinion = agent.analyze(ctx)
    assert not any("TradingView" in e for e in opinion.evidence)
    assert not any("TradingView" in c for c in opinion.caveats)
