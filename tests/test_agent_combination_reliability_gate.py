"""analytics/agent_combination_reliability_gate.py — Faz 367-devam.
Saf fonksiyon testleri (decision_recorder.py wiring'i için bkz. tests/
test_agent_combination_reliability_gate_wiring.py)."""
from analytics.agent_combination_reliability_gate import (
    is_agent_combination_trading_blocked,
    trustworthy_known_pairs,
)

_LOW_PAIR = {
    "domains": ["technical", "quant"], "win_rate": 0.40,
    "fdr_significant": True, "max_shared_trade_overlap_pct": 0.1, "distinct_days": 10,
}
_HIGH_PAIR = {
    "domains": ["onchain", "order_flow"], "win_rate": 0.95,
    "fdr_significant": True, "max_shared_trade_overlap_pct": 0.1, "distinct_days": 10,
}


def test_trustworthy_known_pairs_excludes_non_fdr_significant():
    pairs = [dict(_LOW_PAIR, fdr_significant=False)]
    assert trustworthy_known_pairs(pairs) == []


def test_trustworthy_known_pairs_excludes_high_overlap():
    pairs = [dict(_LOW_PAIR, max_shared_trade_overlap_pct=0.9)]
    assert trustworthy_known_pairs(pairs) == []


def test_trustworthy_known_pairs_keeps_fdr_significant_low_overlap():
    result = trustworthy_known_pairs([_LOW_PAIR, _HIGH_PAIR])
    assert result == [_LOW_PAIR, _HIGH_PAIR]


def test_trustworthy_known_pairs_excludes_narrow_time_window():
    """GPT incelemesi bulgusu: bir grup düşük overlap'e sahip olsa bile
    TÜM işlemleri tek bir dar (ör. 2 günlük) tarihsel pencereden geliyorsa
    'bağımsız kanıt' sayılmamalı."""
    pairs = [dict(_LOW_PAIR, distinct_days=2)]
    assert trustworthy_known_pairs(pairs) == []


def test_trustworthy_known_pairs_excludes_missing_distinct_days():
    pairs = [{k: v for k, v in _LOW_PAIR.items() if k != "distinct_days"}]
    assert trustworthy_known_pairs(pairs) == []


def test_blocked_when_agreeing_domains_is_none():
    assert is_agent_combination_trading_blocked(None, [_LOW_PAIR], min_win_rate=0.80) is False


def test_blocked_when_a_known_pair_is_a_subset_and_below_threshold():
    agreeing = frozenset({"technical", "quant", "macro"})
    assert is_agent_combination_trading_blocked(agreeing, [_LOW_PAIR], min_win_rate=0.80) is True


def test_not_blocked_when_known_pair_is_not_a_subset():
    agreeing = frozenset({"macro", "sentiment"})
    assert is_agent_combination_trading_blocked(agreeing, [_LOW_PAIR], min_win_rate=0.80) is False


def test_not_blocked_when_matching_pair_is_above_threshold():
    agreeing = frozenset({"onchain", "order_flow", "macro"})
    assert is_agent_combination_trading_blocked(agreeing, [_HIGH_PAIR], min_win_rate=0.80) is False


def test_not_blocked_with_empty_known_pairs():
    agreeing = frozenset({"technical", "quant"})
    assert is_agent_combination_trading_blocked(agreeing, [], min_win_rate=0.80) is False


def test_single_low_match_blocks_even_alongside_a_high_match():
    """Birden fazla bilinen grup eşleşirse TEK bir düşük eşleşme yeterli
    — 'iyi bir grup de vardı' bahanesiyle bilinen kötü bir grup görmezden
    gelinmiyor."""
    agreeing = frozenset({"technical", "quant", "onchain", "order_flow"})
    assert is_agent_combination_trading_blocked(agreeing, [_LOW_PAIR, _HIGH_PAIR], min_win_rate=0.80) is True
