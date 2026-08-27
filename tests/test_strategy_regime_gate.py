"""analytics/strategy_regime_gate.py — Faz 366."""
from analytics.strategy_regime_gate import is_strategy_regime_gated


def test_blocks_when_pair_in_approved_set():
    approved = {("ai_council_LONG_swing", "bullish_high")}
    assert is_strategy_regime_gated("ai_council_LONG_swing", "bullish_high", approved) is True


def test_does_not_block_different_regime():
    approved = {("ai_council_LONG_swing", "bullish_high")}
    assert is_strategy_regime_gated("ai_council_LONG_swing", "bullish_low", approved) is False


def test_does_not_block_different_strategy():
    approved = {("ai_council_LONG_swing", "bullish_high")}
    assert is_strategy_regime_gated("ai_council_SHORT_swing", "bullish_high", approved) is False


def test_unknown_regime_never_blocked():
    approved = {("ai_council_LONG_swing", "bullish_high")}
    assert is_strategy_regime_gated("ai_council_LONG_swing", None, approved) is False


def test_empty_approved_set_never_blocks():
    assert is_strategy_regime_gated("ai_council_LONG_swing", "bullish_high", set()) is False
