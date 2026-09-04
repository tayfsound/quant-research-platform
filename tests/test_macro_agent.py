"""Macro Agent testleri."""
from agents.macro_agent import MacroAgent
from contracts.macro import MacroContext


def test_hawkish_macro_generates_short():
    agent = MacroAgent()
    ctx = MacroContext(
        indicators=[],
        inflation_trend="rising",
        liquidity_condition="tight",
        central_bank_bias="hawkish",
        employment_trend="weakening",
    )
    opinion = agent.analyze(ctx)
    assert opinion.domain.value == "macro"
    assert opinion.direction == "SHORT"
    assert opinion.confidence > 0
    assert len(opinion.evidence) >= 2

def test_dovish_macro_generates_long():
    agent = MacroAgent()
    ctx = MacroContext(
        indicators=[],
        inflation_trend="falling",
        liquidity_condition="neutral",
        central_bank_bias="dovish",
    )
    opinion = agent.analyze(ctx)
    assert opinion.direction == "LONG"
    assert opinion.confidence > 0

def test_mixed_macro_generates_wait():
    agent = MacroAgent()
    ctx = MacroContext(
        indicators=[],
        inflation_trend="stable",
        liquidity_condition="neutral",
        central_bank_bias="neutral",
    )
    opinion = agent.analyze(ctx)
    assert opinion.direction == "WAIT"


def test_expanding_net_liquidity_pushes_toward_long():
    """Faz 267: kullanıcı bulgusu — hazine borç/likidite döngüsü
    (Fed bilançosu - TGA - ters repo) genişlerken risk varlıkları için
    destekleyici sayılmalı, tıpkı liquidity_condition="loose" gibi."""
    agent = MacroAgent()
    baseline = MacroContext(indicators=[])
    with_expansion = MacroContext(indicators=[], net_liquidity_trend="expanding")

    score_baseline = agent.analyze(baseline)
    score_expansion = agent.analyze(with_expansion)

    assert score_expansion.direction == "LONG"
    assert "Net likidite" in " ".join(score_expansion.evidence)
    assert score_baseline.direction == "WAIT"


def test_contracting_net_liquidity_pushes_toward_short():
    agent = MacroAgent()
    ctx = MacroContext(indicators=[], net_liquidity_trend="contracting")
    opinion = agent.analyze(ctx)
    assert opinion.direction == "SHORT"


def test_liquidity_condition_no_longer_contributes_to_the_score():
    """Faz 411 (2026-09-04) — kullanıcı isteği: rejime göre ayrıştırılmış
    Feature IC denetiminde liquidity_condition HİÇBİR rejim segmentinde
    anlamlı çıkmadı (gerçekten gürültü) — Faz 408'in "ikincil sinyal"
    uzlaşması yerine tamamen kaldırıldı. Artık ne "loose"/"tight" ne de
    net_liquidity_trend'le çatışması hiçbir şeyi değiştirmiyor — SADECE
    net_liquidity_trend skora giriyor."""
    agent = MacroAgent()
    with_loose = agent.analyze(MacroContext(
        indicators=[], liquidity_condition="loose", net_liquidity_trend="contracting",
    ))
    with_tight = agent.analyze(MacroContext(
        indicators=[], liquidity_condition="tight", net_liquidity_trend="contracting",
    ))
    assert "liquidity_condition" not in with_loose.feature_contributions
    assert with_loose.direction == with_tight.direction == "SHORT"
    assert with_loose.confidence == with_tight.confidence
    assert with_loose.feature_contributions["net_liquidity_trend"] == -1.0


def test_improving_employment_pushes_toward_long():
    """Faz 268h: kritik bulgu — Faz 215'in liquidity_condition için
    düzelttiği asimetri (sadece kötü taraf cezalandırılıyordu) burada da
    vardı. "improving" artık "weakening" ile simetrik ödüllendiriliyor."""
    agent = MacroAgent()
    ctx = MacroContext(indicators=[], employment_trend="improving")
    opinion = agent.analyze(ctx)
    assert opinion.direction == "LONG"
    assert any("iyileşiyor" in e.lower() for e in opinion.evidence)


def test_empty_net_liquidity_trend_contributes_no_score():
    """Veri yoksa (API/key eksik, fetch_net_liquidity_trend None döndü)
    boş string kalır — icat edilmiş bir nötr varsayım değil, sadece
    hiç puan vermiyor."""
    agent = MacroAgent()
    ctx = MacroContext(indicators=[], net_liquidity_trend="")
    opinion = agent.analyze(ctx)
    assert opinion.direction == "WAIT"
    assert not any("Net likidite" in e for e in opinion.evidence)


def test_feature_contributions_sum_to_the_implied_raw_score():
    agent = MacroAgent()
    opinion = agent.analyze(MacroContext(
        indicators=[], inflation_trend="rising", central_bank_bias="hawkish",
    ))
    implied_score = sum(opinion.feature_contributions.values())
    assert abs(abs(implied_score) - opinion.confidence * 3.0) < 5e-3


def test_feature_contributions_are_empty_when_no_signal_fires():
    agent = MacroAgent()
    opinion = agent.analyze(MacroContext(indicators=[]))
    assert opinion.feature_contributions == {}


def test_feature_contributions_names_the_active_signals():
    agent = MacroAgent()
    opinion = agent.analyze(MacroContext(
        indicators=[], inflation_trend="rising",
        central_bank_bias="hawkish", employment_trend="weakening",
    ))
    assert opinion.feature_contributions["inflation"] < 0
    assert opinion.feature_contributions["central_bank_bias"] < 0
    assert opinion.feature_contributions["employment_trend"] < 0
