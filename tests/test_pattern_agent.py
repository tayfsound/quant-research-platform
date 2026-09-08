"""Pattern Agent testleri."""
from agents.pattern_agent import PatternAgent
from contracts.pattern import PatternContext


def test_bullish_bos_generates_short_due_to_empirical_sign_flip():
    """Faz 453 (2026-09-08) — kullanıcı isteği: rejime göre ayrıştırılmış
    gerçek Feature IC denetimi (n=11182, saf 1sa ileri yön hedefine
    karşı) break_of_structure'ın 6 rejimin HEPSİNDE anlamlı NEGATİF IC
    taşıdığını buldu (-0,12 ile -0,28 arası, hepsi p<0,05) — "yükseliş
    yönlü BOS" gerçekte fiyatın DÜŞME olasılığını artırıyor (sahte
    kırılım imzası). İşaret evrensel olarak çevrildi — market_regime
    belirtilmediği (swing_structure/structure_phase'in gölgede kaldığı)
    için SADECE bu sinyalin etkisi izole test ediliyor."""
    agent = PatternAgent()
    opinion = agent.analyze(PatternContext(break_of_structure="bullish"))
    assert opinion.direction == "SHORT"
    assert opinion.confidence > 0


def test_bearish_bos_generates_long_due_to_empirical_sign_flip():
    agent = PatternAgent()
    opinion = agent.analyze(PatternContext(break_of_structure="bearish"))
    assert opinion.direction == "LONG"
    assert opinion.confidence > 0


def test_swing_structure_is_regime_gated():
    """Faz 453 — AYNI denetim: swing_structure wyckoff_event/structure_
    phase İLE AYNI türden rejime GERÇEKTEN bağımlı bir sinyal çıktı
    (bullish_normal'da anlamlı POZİTİF, bullish_low'da anlamlı NEGATİF,
    diğer 4 rejimde anlamsız) — artık _regime_gated() kullanıyor."""
    agent = PatternAgent()
    positive = agent.analyze(PatternContext(
        swing_structure="higher_highs_higher_lows", market_regime="bullish_normal",
    ))
    inverted = agent.analyze(PatternContext(
        swing_structure="higher_highs_higher_lows", market_regime="bullish_low",
    ))
    shadowed = agent.analyze(PatternContext(
        swing_structure="higher_highs_higher_lows", market_regime="bearish_normal",
    ))
    assert positive.direction == "LONG"
    assert positive.feature_contributions["swing_structure"] == 1.0
    assert inverted.direction == "SHORT"
    assert inverted.feature_contributions["swing_structure"] == -1.0
    assert shadowed.direction == "WAIT"
    assert shadowed.feature_contributions["swing_structure"] == 1.0  # gölgede, GERCEK deger korunuyor


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
    """Faz 302/453 — structure_phase/wyckoff_event/swing_structure (bu
    senaryoda market_regime="unknown" olduğu için) artık skora katkı
    vermiyor, feature_ic için gölge olarak kaydediliyor — implied score
    sadece SKORA KATKI VEREN feature'ları kapsamalı."""
    agent = PatternAgent()
    opinion = agent.analyze(PatternContext(
        structure_phase="accumulation", break_of_structure="bullish",
        swing_structure="higher_highs_higher_lows",
    ))
    shadow_keys = {"structure_phase", "wyckoff_event", "swing_structure"}
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


def test_fibonacci_confirmation_no_longer_contributes_to_the_score():
    """Faz 411 (2026-09-04) — kullanıcı isteği: rejime göre ayrıştırılmış
    Feature IC denetiminde fibonacci_confirm HİÇBİR rejim segmentinde
    anlamlı çıkmadı (en yakını bullish_normal'da p=0.083) — gerçekten
    gürültü, mimariden tamamen kaldırıldı."""
    agent = PatternAgent()
    with_support = agent.analyze(PatternContext(
        structure_phase="accumulation", break_of_structure="bullish",
        swing_structure="higher_highs_higher_lows",
        fibonacci_price_position="at_support",
    ))
    without_support = agent.analyze(PatternContext(
        structure_phase="accumulation", break_of_structure="bullish",
        swing_structure="higher_highs_higher_lows",
        fibonacci_price_position="none",
    ))
    assert "fibonacci_confirm" not in with_support.feature_contributions
    assert with_support.confidence == without_support.confidence
