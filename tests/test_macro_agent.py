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


def test_net_liquidity_dominates_when_it_conflicts_with_liquidity_condition():
    """Faz 408 — kullanıcı bulgusu (ölçüm stabilitesi araştırması,
    2026-09-03): macro'nun raw_confidence'ı 1812 gerçek karardan
    HİÇBİRİNDE farklı çıkmıyordu (hep 0.167) — kök neden bug değildi
    (FRED verisi gerçek/güncel), liquidity_condition (M2SL, "loose"
    +1.0) ile net_liquidity_trend ("contracting" -1.0) ~1 aydır sürekli
    TERS yönde çıkıp TAM birbirini götürüyordu, geriye sadece
    employment_trend'in ±0.5'i kalıyordu. Artık net_liquidity_trend
    (daha hızlı/güncel, Faz 267) BASKIN (±1.0), liquidity_condition
    yavaş onaylayıcı (±0.5) — çatıştıklarında TAM iptal yerine net
    likidite ağır basmalı."""
    agent = MacroAgent()
    # Gerçek canlı durum: M2SL "loose" (+), net likidite "contracting" (-).
    ctx = MacroContext(
        indicators=[], liquidity_condition="loose", net_liquidity_trend="contracting",
    )
    opinion = agent.analyze(ctx)
    # Eskiden (±1.0/±1.0) bu ikisi TAM birbirini götürürdü (net 0.0).
    # Artık net_liquidity_trend (±1.0) ağır basıp SHORT'a çekmeli.
    assert opinion.direction == "SHORT"
    assert opinion.feature_contributions["net_liquidity_trend"] == -1.0
    assert opinion.feature_contributions["liquidity_condition"] == 0.5


def test_liquidity_signals_still_fully_agree_when_pointing_the_same_way():
    """Regresyon: ikisi AYNI yönde çıkarsa (M2SL loose + net likidite
    expanding) hâlâ güçlü şekilde birleşmeli — sadece ÇATIŞMA durumunda
    net_liquidity_trend ağır basıyor, aynı yöndeyken ikisi de katkı verir."""
    agent = MacroAgent()
    ctx = MacroContext(
        indicators=[], liquidity_condition="loose", net_liquidity_trend="expanding",
    )
    opinion = agent.analyze(ctx)
    assert opinion.direction == "LONG"
    assert opinion.feature_contributions["net_liquidity_trend"] == 1.0
    assert opinion.feature_contributions["liquidity_condition"] == 0.5


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
        indicators=[], inflation_trend="rising", liquidity_condition="tight",
        central_bank_bias="hawkish", employment_trend="weakening",
    ))
    assert opinion.feature_contributions["inflation"] < 0
    assert opinion.feature_contributions["liquidity_condition"] < 0
    assert opinion.feature_contributions["central_bank_bias"] < 0
    assert opinion.feature_contributions["employment_trend"] < 0
