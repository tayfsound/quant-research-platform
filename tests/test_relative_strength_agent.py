"""Faz 242-243: Relative Strength Agent (10. oy-veren ajan)."""
from agents.relative_strength_agent import RelativeStrengthAgent
from contracts.relative_strength import RelativeStrengthContext


def test_waits_when_basket_has_fewer_than_three_peers():
    agent = RelativeStrengthAgent()
    opinion = agent.analyze(RelativeStrengthContext(
        basket_size=2, symbol_return_pct=0.05, basket_mean_return_pct=0.0, relative_strength_pct=0.05,
    ))
    assert opinion.direction == "WAIT"
    assert opinion.confidence == 0.0
    assert "watchlist" in opinion.caveats[0].lower() or "veri" in opinion.caveats[0].lower()


def test_goes_long_when_meaningfully_outperforming_the_basket():
    agent = RelativeStrengthAgent()
    opinion = agent.analyze(RelativeStrengthContext(
        basket_size=5, symbol_return_pct=0.10, basket_mean_return_pct=0.0, relative_strength_pct=0.10,
    ))
    assert opinion.direction == "LONG"
    assert opinion.confidence > 0
    assert len(opinion.evidence) == 1


def test_goes_short_when_meaningfully_underperforming_the_basket():
    agent = RelativeStrengthAgent()
    opinion = agent.analyze(RelativeStrengthContext(
        basket_size=5, symbol_return_pct=-0.08, basket_mean_return_pct=0.02, relative_strength_pct=-0.10,
    ))
    assert opinion.direction == "SHORT"
    assert opinion.confidence > 0


def test_waits_when_divergence_is_within_noise_threshold():
    agent = RelativeStrengthAgent()
    opinion = agent.analyze(RelativeStrengthContext(
        basket_size=5, symbol_return_pct=0.011, basket_mean_return_pct=0.005, relative_strength_pct=0.006,
    ))
    assert opinion.direction == "WAIT"


def test_confidence_is_capped_at_0_85_even_for_extreme_divergence():
    agent = RelativeStrengthAgent()
    opinion = agent.analyze(RelativeStrengthContext(
        basket_size=5, symbol_return_pct=1.0, basket_mean_return_pct=0.0, relative_strength_pct=1.0,
    ))
    assert opinion.confidence <= 0.85


def test_confidence_scales_with_divergence_magnitude():
    agent = RelativeStrengthAgent()
    small = agent.analyze(RelativeStrengthContext(
        basket_size=5, symbol_return_pct=0.015, basket_mean_return_pct=0.0, relative_strength_pct=0.015,
    ))
    large = agent.analyze(RelativeStrengthContext(
        basket_size=5, symbol_return_pct=0.05, basket_mean_return_pct=0.0, relative_strength_pct=0.05,
    ))
    assert large.confidence > small.confidence


def test_opinion_domain_is_relative_strength():
    from contracts.agent import AgentDomain

    agent = RelativeStrengthAgent()
    opinion = agent.analyze(RelativeStrengthContext(basket_size=0))
    assert opinion.domain == AgentDomain.RELATIVE_STRENGTH
