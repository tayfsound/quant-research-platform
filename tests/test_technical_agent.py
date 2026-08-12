"""Technical Agent testleri."""
from agents.technical_agent import TechnicalAgent
from contracts.technical import TechnicalContext


def test_bullish_setup_generates_long():
    agent = TechnicalAgent()
    ctx = TechnicalContext(
        trend="bullish",
        momentum="strengthening",
        market_structure="higher_highs",
        volume_confirmation=True,
        ema_alignment="bullish_aligned",
    )
    opinion = agent.analyze(ctx)
    assert opinion.direction == "LONG"
    assert opinion.confidence > 0
    assert len(opinion.evidence) >= 2

def test_bearish_setup_generates_short():
    agent = TechnicalAgent()
    ctx = TechnicalContext(
        trend="bearish",
        momentum="weakening",
        market_structure="lower_lows",
        rsi_value=80.0,
    )
    opinion = agent.analyze(ctx)
    assert opinion.direction == "SHORT"
    assert opinion.confidence > 0

def test_ranging_market_waits():
    agent = TechnicalAgent()
    ctx = TechnicalContext(
        trend="neutral",
        momentum="neutral",
        market_structure="ranging",
    )
    opinion = agent.analyze(ctx)
    assert opinion.direction == "WAIT"

def test_volume_confirmation_no_longer_rewarded_as_bullish():
    """Faz 258: kritik bulgu — feature importance analizi (561 gerçek
    kapanmış işlem) volume_confirmation=True'nun aslında DAHA KÖTÜ
    sonuçla ilişkili olduğunu gösterdi (%15.4 vs %28.5 kazanma oranı).
    Bu test, volume_confirmation=True'nun artık bullish bir teyit olarak
    puanlanmadığını (aksine hafif negatif) kanıtlıyor."""
    agent = TechnicalAgent()

    ctx_with_spike = TechnicalContext(
        trend="bullish", momentum="strengthening", market_structure="higher_highs",
        volume_confirmation=True,
    )
    ctx_without_spike = TechnicalContext(
        trend="bullish", momentum="strengthening", market_structure="higher_highs",
        volume_confirmation=False,
    )

    opinion_with_spike = agent.analyze(ctx_with_spike)
    opinion_without_spike = agent.analyze(ctx_without_spike)

    assert not any("confirms trend" in e for e in opinion_with_spike.evidence)
    assert any("volume spike" in c.lower() for c in opinion_with_spike.caveats)
    # Aynı diğer koşullarda, hacim sıçraması OLAN senaryo artık OLMAYANDAN
    # daha düşük konviksiyonlu olmalı (önceden tam tersiydi).
    assert opinion_with_spike.confidence < opinion_without_spike.confidence


def test_volume_divergence_warning():
    agent = TechnicalAgent()
    ctx = TechnicalContext(
        trend="bullish",
        momentum="strengthening",
        market_structure="higher_highs",
        volume_confirmation=False,
    )
    opinion = agent.analyze(ctx)
    assert any("Volume not confirming" in c for c in opinion.caveats)


def test_confirming_tradingview_signal_adds_evidence_not_a_new_direction():
    """Faz 193: TradingView ikinci görüş — kendi hesapladığı yönü teyit
    ederse evidence'a eklenir, yönü DEĞİŞTİRMEZ."""
    agent = TechnicalAgent()
    ctx = TechnicalContext(
        trend="bullish", momentum="strengthening", market_structure="higher_highs",
        external_signal="bullish", external_signal_source="tradingview",
    )
    opinion = agent.analyze(ctx)
    assert opinion.direction == "LONG"
    assert any("TradingView" in e for e in opinion.evidence)


def test_conflicting_tradingview_signal_adds_caveat_not_a_direction_flip():
    """TradingView kendi iç görüşle çelişirse sadece bir uyarı (caveat)
    eklenir — tek başına yönü LONG'dan SHORT'a çevirmez."""
    agent = TechnicalAgent()
    ctx = TechnicalContext(
        trend="bullish", momentum="strengthening", market_structure="higher_highs",
        external_signal="bearish", external_signal_source="tradingview",
    )
    opinion = agent.analyze(ctx)
    assert opinion.direction == "LONG"  # kendi iç görüşü hâlâ geçerli
    assert any("çelişiyor" in c for c in opinion.caveats)


def test_no_external_signal_means_no_extra_evidence_or_caveat():
    agent = TechnicalAgent()
    ctx = TechnicalContext(trend="bullish", momentum="strengthening", market_structure="higher_highs")
    opinion = agent.analyze(ctx)
    assert not any("TradingView" in e for e in opinion.evidence)
    assert not any("TradingView" in c for c in opinion.caveats)


def test_feature_contributions_sum_to_the_implied_raw_score():
    """Faz 268-sonrası: Feature Importance — feature_contributions her
    zaman GERÇEK score'a (confidence = min(|score|/5.0, 0.85)) eşit
    toplanmalı, tıpkı QuantAgent'ta olduğu gibi."""
    agent = TechnicalAgent()
    opinion = agent.analyze(TechnicalContext(
        trend="bullish", momentum="strengthening", market_structure="higher_highs",
        ema_alignment="bullish_aligned", adx=10.0,
    ))
    implied_score = sum(opinion.feature_contributions.values())
    assert abs(abs(implied_score) - opinion.confidence * 5.0) < 1e-6


def test_feature_contributions_are_empty_when_no_signal_fires():
    agent = TechnicalAgent()
    opinion = agent.analyze(TechnicalContext())  # tüm varsayılanlar -> hiçbir dal tetiklenmez
    assert opinion.feature_contributions == {}


def test_feature_contributions_names_the_active_signals():
    agent = TechnicalAgent()
    opinion = agent.analyze(TechnicalContext(
        trend="bullish", momentum="strengthening", market_structure="higher_highs",
        ema_alignment="bullish_aligned", adx=30.0, di_plus=30.0, di_minus=10.0,
    ))
    assert opinion.feature_contributions["trend"] > 0
    assert opinion.feature_contributions["momentum"] > 0
    assert opinion.feature_contributions["market_structure"] > 0
    assert opinion.feature_contributions["ema_alignment"] > 0
    assert opinion.feature_contributions["adx_strong_confirm"] > 0


def test_feature_contributions_reflect_the_adx_weak_discount():
    """ADX<20 iken scale_all(adx_weak_discount) O ANA KADAR birikmiş TÜM
    katkılara uygulanmalı — orijinal `score *= c.adx_weak_discount` ile
    birebir aynı sıralama/etki."""
    agent = TechnicalAgent()
    no_discount = agent.analyze(TechnicalContext(trend="bullish", adx=22.0))
    with_discount = agent.analyze(TechnicalContext(trend="bullish", adx=10.0))
    assert abs(with_discount.feature_contributions["trend"] - no_discount.feature_contributions["trend"] * 0.7) < 1e-6
