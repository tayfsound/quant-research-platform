"""Opportunity Quality / Meta-Labeling testleri — Faz 569-593 (Cognitive Core 2.0)."""
from analytics.opportunity_quality import (
    agreement_from_contributions,
    agreement_from_opinions,
    compute_agent_agreement,
    compute_opportunity_quality_by_agreement,
)


def test_unanimous_vote_scores_full_agreement():
    result = compute_agent_agreement({"LONG": 9, "SHORT": 0, "WAIT": 0})
    assert result == 1.0


def test_evenly_split_vote_scores_zero_agreement():
    result = compute_agent_agreement({"LONG": 3, "SHORT": 3, "WAIT": 3})
    assert abs(result) < 1e-9


def test_partial_agreement_is_between_zero_and_one():
    result = compute_agent_agreement({"LONG": 6, "SHORT": 2, "WAIT": 1})
    assert 0.0 < result < 1.0


def test_no_votes_returns_zero_fail_closed():
    assert compute_agent_agreement({"LONG": 0, "SHORT": 0, "WAIT": 0}) == 0.0


def _trade(agreement: float, win: bool) -> dict:
    return {"agent_agreement": agreement, "win": win}


def test_opportunity_quality_detects_higher_win_rate_with_higher_agreement():
    trades = (
        [_trade(0.9, True) for _ in range(18)] + [_trade(0.9, False) for _ in range(2)]  # high: %90
        + [_trade(0.1, True) for _ in range(8)] + [_trade(0.1, False) for _ in range(12)]  # low: %40
    )
    result = compute_opportunity_quality_by_agreement(trades, min_group_size=20)
    assert result["high"]["win_rate"] > result["low"]["win_rate"]


def test_opportunity_quality_win_rate_ci_contains_the_point_estimate():
    """Faz 305 — Collective Intelligence/Agent Ablation'daki AYNI desen:
    n=20'de bile win_rate nokta tahmini geniş bir bant içinde belirsiz
    olabilir, Wilson aralığı bilgilendirme amaçlı ekleniyor."""
    trades = [_trade(0.9, True) for _ in range(18)] + [_trade(0.9, False) for _ in range(2)]
    result = compute_opportunity_quality_by_agreement(trades, min_group_size=20)
    ci = result["high"]["win_rate_ci"]
    assert ci is not None
    assert ci["low"] <= result["high"]["win_rate"] <= ci["high"]


def test_below_min_group_size_is_excluded_fail_closed():
    trades = [_trade(0.9, True) for _ in range(5)]
    result = compute_opportunity_quality_by_agreement(trades, min_group_size=20)
    assert result == {}


def test_trades_missing_agreement_or_win_are_skipped_without_crashing():
    trades = [{"agent_agreement": None, "win": True}] * 25
    result = compute_opportunity_quality_by_agreement(trades, min_group_size=5)
    assert result == {}


def test_agreement_from_contributions_counts_domain_votes():
    contributions = [
        {"domain": "technical", "direction": "LONG"},
        {"domain": "macro", "direction": "LONG"},
        {"domain": "quant", "direction": "SHORT"},
        {"type": "risk_evaluation", "data": {}},  # domain'siz, oy DEĞİL — atlanmalı
    ]
    result = agreement_from_contributions(contributions)
    assert result == compute_agent_agreement({"LONG": 2, "SHORT": 1, "WAIT": 0})


def test_agreement_from_contributions_returns_none_without_any_votes():
    assert agreement_from_contributions([{"type": "market_snapshot", "data": {}}]) is None
    assert agreement_from_contributions(None) is None
    assert agreement_from_contributions([]) is None


def test_agreement_from_opinions_matches_agreement_from_contributions():
    """Faz 350 — kritik tutarlılık: eğitim (contributions dict) ve canlı
    tahmin (opinions nesnesi) AYNI oy setinde AYNI skoru üretmeli, aksi
    halde model eğitildiği dağılımı canlıda hiç göremez."""
    from contracts.agent import AgentDomain, AgentOpinion

    opinions = [
        AgentOpinion(domain=AgentDomain.TECHNICAL, direction="LONG"),
        AgentOpinion(domain=AgentDomain.MACRO, direction="LONG"),
        AgentOpinion(domain=AgentDomain.QUANT, direction="SHORT"),
    ]
    contributions = [{"domain": o.domain.value, "direction": o.direction} for o in opinions]

    assert agreement_from_opinions(opinions) == agreement_from_contributions(contributions)


def test_agreement_from_opinions_returns_none_for_empty_list():
    assert agreement_from_opinions([]) is None
    assert agreement_from_opinions(None) is None


def test_reliability_from_contributions_averages_only_agreeing_domains():
    from analytics.opportunity_quality import _reliability_from_contributions

    contributions = [
        {"domain": "technical", "direction": "LONG", "source_reliability": 0.8},
        {"domain": "macro", "direction": "LONG", "source_reliability": 0.6},
        {"domain": "quant", "direction": "SHORT", "source_reliability": 0.95},  # anlaşmıyor, dışlanır
    ]
    result = _reliability_from_contributions(contributions, "LONG")
    assert abs(result - 0.7) < 1e-9  # (0.8+0.6)/2


def test_reliability_from_contributions_none_when_no_agreeing_domain_has_reliability():
    from analytics.opportunity_quality import _reliability_from_contributions

    contributions = [{"domain": "technical", "direction": "LONG"}]  # source_reliability yok
    assert _reliability_from_contributions(contributions, "LONG") is None


def test_reliability_from_contributions_none_for_non_directional_final():
    from analytics.opportunity_quality import _reliability_from_contributions

    contributions = [{"domain": "technical", "direction": "LONG", "source_reliability": 0.8}]
    assert _reliability_from_contributions(contributions, "WAIT") is None


def test_quality_score_is_product_of_agreement_and_reliability():
    from analytics.opportunity_quality import compute_quality_score

    assert compute_quality_score(0.8, 0.5) == 0.4
    assert compute_quality_score(1.0, 1.0) == 1.0
    assert compute_quality_score(0.0, 0.9) == 0.0


def test_opportunity_quality_by_score_reports_expectancy_median_and_profit_factor():
    from analytics.opportunity_quality import compute_opportunity_quality_by_score

    trades = (
        [{"quality_score": 0.9, "win": True, "pnl": 100.0} for _ in range(15)]
        + [{"quality_score": 0.9, "win": False, "pnl": -20.0} for _ in range(5)]
    )
    result = compute_opportunity_quality_by_score(trades, min_group_size=15)
    high = result["high"]["overall"]
    assert high["sample_size"] == 20
    assert high["win_rate"] == 0.75
    assert abs(high["expectancy"] - (15 * 100 - 5 * 20) / 20) < 1e-9
    assert high["median_pnl"] == 100.0
    assert abs(high["profit_factor"] - (1500 / 100)) < 1e-9


def test_opportunity_quality_by_score_profit_factor_is_none_without_losses():
    from analytics.opportunity_quality import compute_opportunity_quality_by_score

    trades = [{"quality_score": 0.9, "win": True, "pnl": 10.0} for _ in range(20)]
    result = compute_opportunity_quality_by_score(trades, min_group_size=20)
    assert result["high"]["overall"]["profit_factor"] is None


def test_opportunity_quality_by_score_splits_by_regime_with_own_min_group_size():
    from analytics.opportunity_quality import compute_opportunity_quality_by_score

    trades = (
        [{"quality_score": 0.9, "win": True, "pnl": 10.0, "market_regime": "bullish_low"} for _ in range(25)]
        + [{"quality_score": 0.9, "win": False, "pnl": -5.0, "market_regime": "bearish_low"} for _ in range(3)]  # eşiğin altında
    )
    result = compute_opportunity_quality_by_score(trades, min_group_size=20)
    assert result["high"]["overall"]["sample_size"] == 28
    assert "bullish_low" in result["high"]["by_regime"]
    assert "bearish_low" not in result["high"]["by_regime"]  # kendi eşiğini geçemedi


def test_opportunity_quality_by_score_excludes_trades_without_score():
    from analytics.opportunity_quality import compute_opportunity_quality_by_score

    trades = [{"win": True, "pnl": 10.0} for _ in range(20)]  # quality_score yok
    assert compute_opportunity_quality_by_score(trades, min_group_size=20) == {}
