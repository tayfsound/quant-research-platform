"""Macro Agent testleri."""
from agents.macro_agent import MacroAgent
from contracts.macro import MacroContext

def test_hawkish_macro_generates_short():
    agent = MacroAgent()
    ctx = MacroContext(
        indicators=[],
        inflation_trend="rising",
        liquidity_condition="tight",
        central_bank_bias="hawkish",
        employment_trend="weakening",
    )
    opinion = agent.analyze(ctx)
    assert opinion.domain.value == "macro"
    assert opinion.direction == "SHORT"
    assert opinion.confidence > 0
    assert len(opinion.evidence) >= 2

def test_dovish_macro_generates_long():
    agent = MacroAgent()
    ctx = MacroContext(
        indicators=[],
        inflation_trend="falling",
        liquidity_condition="neutral",
        central_bank_bias="dovish",
    )
    opinion = agent.analyze(ctx)
    assert opinion.direction == "LONG"
    assert opinion.confidence > 0

def test_mixed_macro_generates_wait():
    agent = MacroAgent()
    ctx = MacroContext(
        indicators=[],
        inflation_trend="stable",
        liquidity_condition="neutral",
        central_bank_bias="neutral",
    )
    opinion = agent.analyze(ctx)
    assert opinion.direction == "WAIT"
