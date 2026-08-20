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

    assert not any("teyit ediyor" in e for e in opinion_with_spike.evidence)
    assert any("hacim sıçraması" in c.lower() for c in opinion_with_spike.caveats)
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
    assert any("Hacim trendi teyit etmiyor" in c for c in opinion.caveats)


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


def test_htf_agreement_discounts_confidence_but_never_changes_direction():
    """Faz 316 — gerçek geçmiş veri ölçümü: kısa-vadeli yön 4h trendle
    AYNIYKEN kazanma oranı daha düşük (%41.6) — confidence indirilmeli,
    direction ASLA değişmemeli."""
    agent = TechnicalAgent()
    base_ctx = TechnicalContext(
        trend="bullish", momentum="strengthening", market_structure="higher_highs",
        ema_alignment="bullish_aligned",
    )
    baseline = agent.analyze(base_ctx)
    agreeing = agent.analyze(base_ctx.model_copy(update={"higher_timeframe_trend": "bullish"}))

    assert baseline.direction == "LONG"
    assert agreeing.direction == "LONG"
    assert agreeing.confidence < baseline.confidence
    assert abs(agreeing.confidence - round(baseline.confidence * 0.75, 3)) < 1e-3


def test_htf_disagreement_boosts_confidence_but_never_changes_direction():
    """Aynı ölçüm: kısa-vadeli yön 4h trendin TERSİNDEYKEN kazanma oranı
    daha yüksek (%74.7) — confidence artırılmalı (0.85 tavanı korunarak),
    direction ASLA değişmemeli."""
    agent = TechnicalAgent()
    base_ctx = TechnicalContext(
        trend="bearish", momentum="weakening", market_structure="lower_lows",
        rsi_value=80.0,
    )
    baseline = agent.analyze(base_ctx)
    disagreeing = agent.analyze(base_ctx.model_copy(update={"higher_timeframe_trend": "bullish"}))

    assert baseline.direction == "SHORT"
    assert disagreeing.direction == "SHORT"
    assert disagreeing.confidence >= baseline.confidence
    assert disagreeing.confidence <= 0.85


def test_htf_trend_missing_or_neutral_never_changes_confidence():
    """higher_timeframe_trend None (veri yok) ya da 'neutral' (ölçümde
    hiç örneklenmemiş kova) iken hiçbir ayarlama yapılmamalı — no-op."""
    agent = TechnicalAgent()
    base_ctx = TechnicalContext(trend="bullish", momentum="strengthening", market_structure="higher_highs")
    baseline = agent.analyze(base_ctx)

    none_case = agent.analyze(base_ctx.model_copy(update={"higher_timeframe_trend": None}))
    neutral_case = agent.analyze(base_ctx.model_copy(update={"higher_timeframe_trend": "neutral"}))

    assert none_case.confidence == baseline.confidence
    assert neutral_case.confidence == baseline.confidence


def test_htf_signal_never_fires_on_wait():
    """direction WAIT iken (score eşiği geçmedi) htf sinyali hiç
    devreye girmemeli — sadece yönlü (LONG/SHORT) çağrılarda anlamlı."""
    agent = TechnicalAgent()
    ctx = TechnicalContext(trend="neutral", higher_timeframe_trend="bullish")
    opinion = agent.analyze(ctx)
    assert opinion.direction == "WAIT"
