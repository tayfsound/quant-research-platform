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


def test_suspected_price_spike_manipulation_raises_confidence_and_warns():
    """Faz 268-sonrası: Data Quality Scoring — signal_engine.compute_
    data_quality_score'un tespit ettiği kötü print/fitil manipülasyonu
    şüphesi, data_age_seconds ile AYNI desende güveni artırmalı."""
    agent = EpistemologyAgent()
    clean = agent.analyze(EpistemologyContext(feature_completeness=0.9, data_quality_score=1.0))
    suspect = agent.analyze(EpistemologyContext(feature_completeness=0.9, data_quality_score=0.6))
    assert suspect.confidence > clean.confidence
    assert any("data quality" in c.lower() for c in suspect.caveats)


def test_data_quality_field_is_the_more_pessimistic_of_the_two_signals():
    """feature_completeness ve data_quality_score BAĞIMSIZ iki sinyal —
    biri iyi görünürken diğerinin gerçek bir sorunu maskelemesi
    (ortalamayla yumuşatılması) fail-fake olurdu, min alınmalı."""
    agent = EpistemologyAgent()
    opinion = agent.analyze(EpistemologyContext(feature_completeness=0.95, data_quality_score=0.5))
    assert opinion.data_quality == 0.5


def test_imminent_high_impact_event_raises_confidence_and_warns():
    """Faz 271-sonrası: Economic Calendar Integration — FOMC/CPI gibi
    yüksek etkili bir yayın yakınken, data_quality_score ile AYNI desende
    güveni artırmalı."""
    agent = EpistemologyAgent()
    calm = agent.analyze(EpistemologyContext(feature_completeness=0.9, high_impact_event_imminent=False))
    imminent = agent.analyze(EpistemologyContext(feature_completeness=0.9, high_impact_event_imminent=True))
    assert imminent.confidence > calm.confidence
    assert any("fomc" in c.lower() or "cpi" in c.lower() for c in imminent.caveats)
