"""analytics/agent_combination_reliability_gate.py — Faz 367-devam.
Saf fonksiyon testleri (decision_recorder.py wiring'i için bkz. tests/
test_agent_combination_reliability_gate_wiring.py)."""
from analytics.agent_combination_reliability_gate import (
    force_open_eligible_pairs,
    is_agent_combination_force_eligible,
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


# Faz 392 — force-open yönü (blok yönünün simetriği). _HIGH_PAIR win_rate
# 0.95 ama gate_eligible varsayılan olarak yok (aşağıdaki testlerde
# ekleniyor) — force_open_eligible_pairs, trustworthy_known_pairs'ın
# ÜSTÜNE ayrıca gate_eligible + yüksek win_rate şartı ekliyor.
_GATE_ELIGIBLE_HIGH_PAIR = {**_HIGH_PAIR, "gate_eligible": True}
_NOT_GATE_ELIGIBLE_HIGH_PAIR = {**_HIGH_PAIR, "gate_eligible": False}


def test_force_open_eligible_pairs_excludes_non_gate_eligible_even_if_high_win_rate():
    result = force_open_eligible_pairs([_NOT_GATE_ELIGIBLE_HIGH_PAIR], min_win_rate=0.85)
    assert result == []


def test_force_open_eligible_pairs_excludes_gate_eligible_below_min_win_rate():
    low_but_gate_eligible = {**_LOW_PAIR, "gate_eligible": True}
    result = force_open_eligible_pairs([low_but_gate_eligible], min_win_rate=0.85)
    assert result == []


def test_force_open_eligible_pairs_keeps_gate_eligible_high_win_rate():
    result = force_open_eligible_pairs([_GATE_ELIGIBLE_HIGH_PAIR], min_win_rate=0.85)
    assert result == [_GATE_ELIGIBLE_HIGH_PAIR]


def test_force_open_eligible_pairs_still_applies_trustworthy_filters():
    """gate_eligible + yüksek win_rate yetmiyor — bağımsızlık kanıtı
    (overlap/distinct_days) da hâlâ geçerli, çünkü trustworthy_known_
    pairs önce çalışıyor."""
    narrow_window = {**_GATE_ELIGIBLE_HIGH_PAIR, "distinct_days": 2}
    assert force_open_eligible_pairs([narrow_window], min_win_rate=0.85) == []


def test_force_eligible_when_agreeing_domains_is_none():
    eligible, matched = is_agent_combination_force_eligible(None, [_GATE_ELIGIBLE_HIGH_PAIR])
    assert eligible is False
    assert matched is None


def test_force_eligible_when_known_pair_is_a_subset():
    agreeing = frozenset({"onchain", "order_flow", "macro"})
    eligible, matched = is_agent_combination_force_eligible(agreeing, [_GATE_ELIGIBLE_HIGH_PAIR])
    assert eligible is True
    assert matched == _GATE_ELIGIBLE_HIGH_PAIR


def test_not_force_eligible_when_known_pair_is_not_a_subset():
    agreeing = frozenset({"macro", "sentiment"})
    eligible, matched = is_agent_combination_force_eligible(agreeing, [_GATE_ELIGIBLE_HIGH_PAIR])
    assert eligible is False
    assert matched is None


def test_force_eligible_returns_the_strongest_match_when_multiple_qualify():
    stronger_pair = {**_GATE_ELIGIBLE_HIGH_PAIR, "domains": ["macro"], "win_rate": 0.99}
    agreeing = frozenset({"onchain", "order_flow", "macro"})
    eligible, matched = is_agent_combination_force_eligible(
        agreeing, [_GATE_ELIGIBLE_HIGH_PAIR, stronger_pair]
    )
    assert eligible is True
    assert matched["win_rate"] == 0.99
