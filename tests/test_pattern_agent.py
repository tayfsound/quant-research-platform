"""Pattern Agent testleri."""
from agents.pattern_agent import PatternAgent
from contracts.pattern import PatternContext


def test_accumulation_with_bullish_bos_generates_long():
    agent = PatternAgent()
    ctx = PatternContext(
        structure_phase="accumulation",
        break_of_structure="bullish",
        swing_structure="higher_highs_higher_lows",
    )
    opinion = agent.analyze(ctx)
    assert opinion.direction == "LONG"
    assert opinion.confidence > 0
    assert len(opinion.evidence) >= 2


def test_distribution_with_bearish_bos_generates_short():
    agent = PatternAgent()
    ctx = PatternContext(
        structure_phase="distribution",
        break_of_structure="bearish",
        swing_structure="lower_highs_lower_lows",
    )
    opinion = agent.analyze(ctx)
    assert opinion.direction == "SHORT"
    assert opinion.confidence > 0


def test_change_of_character_dampens_confidence():
    agent = PatternAgent()
    with_choch = agent.analyze(PatternContext(
        structure_phase="accumulation", break_of_structure="bullish",
        swing_structure="higher_highs_higher_lows", change_of_character=True,
    ))
    without_choch = agent.analyze(PatternContext(
        structure_phase="accumulation", break_of_structure="bullish",
        swing_structure="higher_highs_higher_lows", change_of_character=False,
    ))
    assert with_choch.confidence < without_choch.confidence
    assert any("Change of character" in c for c in with_choch.caveats)


def test_mixed_structure_waits():
    agent = PatternAgent()
    opinion = agent.analyze(PatternContext())
    assert opinion.direction == "WAIT"
