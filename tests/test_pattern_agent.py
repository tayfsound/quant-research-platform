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
    assert any("Karakter değişimi" in c for c in with_choch.caveats)


def test_mixed_structure_waits():
    agent = PatternAgent()
    opinion = agent.analyze(PatternContext())
    assert opinion.direction == "WAIT"


def test_feature_contributions_sum_to_the_implied_raw_score():
    """Faz 302 — structure_phase/wyckoff_event artık skora katkı vermiyor
    (ampirik ters IC nedeniyle sıfırlandı, feature_ic için gölge olarak
    kaydediliyor) — implied score sadece SKORA KATKI VEREN feature'ları
    kapsamalı."""
    agent = PatternAgent()
    opinion = agent.analyze(PatternContext(
        structure_phase="accumulation", break_of_structure="bullish",
        swing_structure="higher_highs_higher_lows",
    ))
    shadow_keys = {"structure_phase", "wyckoff_event"}
    implied_score = sum(v for k, v in opinion.feature_contributions.items() if k not in shadow_keys)
    assert abs(abs(implied_score) - opinion.confidence * 5.0) < 1e-6


def test_feature_contributions_are_empty_when_no_signal_fires():
    agent = PatternAgent()
    opinion = agent.analyze(PatternContext())
    assert opinion.feature_contributions == {}


def test_feature_contributions_reflect_the_change_of_character_discount():
    """scale_all(0.6) SADECE skora katkı veren contributions'a (break_of_
    structure) uygulanır — structure_phase artık gölge (skora katkısı
    sıfır, Faz 302) olduğu için CHoCH'tan ETKİLENMEMELİ; sonradan eklenen
    swing_structure katkısı da ETKİLENMEMELİ, orijinal `score *= 0.6`'nın
    tam sıralamasıyla birebir aynı."""
    agent = PatternAgent()
    without_choch = agent.analyze(PatternContext(
        structure_phase="accumulation", break_of_structure="bullish",
        swing_structure="higher_highs_higher_lows", change_of_character=False,
    ))
    with_choch = agent.analyze(PatternContext(
        structure_phase="accumulation", break_of_structure="bullish",
        swing_structure="higher_highs_higher_lows", change_of_character=True,
    ))
    assert with_choch.feature_contributions["structure_phase"] == without_choch.feature_contributions["structure_phase"]
    assert abs(with_choch.feature_contributions["break_of_structure"] - without_choch.feature_contributions["break_of_structure"] * 0.6) < 1e-6
    assert with_choch.feature_contributions["swing_structure"] == without_choch.feature_contributions["swing_structure"]


def test_structure_phase_alone_no_longer_influences_direction():
    """Faz 302 — ampirik ters IC nedeniyle (bkz. analytics/feature_ic.py
    bulgusu) skora katkısı sıfırlandı; structure_phase tek başına artık
    WAIT üretmeli (önceden accumulation tek başına +1.5 ile LONG üretirdi)
    ama gerçek (sıfırlanmamış) değer feature_ic'in izlemeye devam edebilmesi
    için feature_contributions'ta gölge olarak kalmalı."""
    agent = PatternAgent()
    opinion = agent.analyze(PatternContext(structure_phase="accumulation"))
    assert opinion.direction == "WAIT"
    assert opinion.feature_contributions["structure_phase"] == 1.5


def test_wyckoff_event_alone_no_longer_influences_direction():
    agent = PatternAgent()
    opinion = agent.analyze(PatternContext(wyckoff_event="spring"))
    assert opinion.direction == "WAIT"
    assert opinion.feature_contributions["wyckoff_event"] == 2.0


def test_feature_contributions_reflect_the_fibonacci_confirmation():
    agent = PatternAgent()
    opinion = agent.analyze(PatternContext(
        structure_phase="accumulation", break_of_structure="bullish",
        swing_structure="higher_highs_higher_lows",
        fibonacci_price_position="at_support",
    ))
    assert opinion.feature_contributions["fibonacci_confirm"] == 0.5
