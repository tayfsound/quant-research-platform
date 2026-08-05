"""Epistemology Agent testleri — yön tahmini yapmaz, veri tamlığını ölçer."""
from agents.epistemology_agent import EpistemologyAgent
from contracts.epistemology import EpistemologyContext


def test_always_waits_regardless_of_input():
    agent = EpistemologyAgent()
    for ctx in (
        EpistemologyContext(feature_completeness=1.0),
        EpistemologyContext(feature_completeness=0.1),
    ):
        assert agent.analyze(ctx).direction == "WAIT"


def test_low_completeness_raises_confidence_and_warns():
    agent = EpistemologyAgent()
    complete = agent.analyze(EpistemologyContext(feature_completeness=0.9, known_unknown_count=0))
    incomplete = agent.analyze(EpistemologyContext(feature_completeness=0.3, known_unknown_count=3))
    assert incomplete.confidence > complete.confidence
    assert any("critically low" in c.lower() for c in incomplete.caveats)


def test_stale_data_raises_confidence():
    agent = EpistemologyAgent()
    fresh = agent.analyze(EpistemologyContext(feature_completeness=0.9, data_age_seconds=10))
    stale = agent.analyze(EpistemologyContext(feature_completeness=0.9, data_age_seconds=600))
    assert stale.confidence > fresh.confidence
    assert any("stale" in c.lower() for c in stale.caveats)


def test_data_quality_reflects_completeness():
    agent = EpistemologyAgent()
    opinion = agent.analyze(EpistemologyContext(feature_completeness=0.6))
    assert opinion.data_quality == 0.6
