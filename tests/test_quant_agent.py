"""Quant Agent testleri."""
from agents.quant_agent import QuantAgent
from contracts.quant import QuantContext


def test_oversold_in_mean_reverting_regime_generates_long():
    agent = QuantAgent()
    ctx = QuantContext(zscore=-2.5, hurst_exponent=0.3)
    opinion = agent.analyze(ctx)
    assert opinion.direction == "LONG"
    assert opinion.confidence > 0


def test_overbought_in_mean_reverting_regime_generates_short():
    agent = QuantAgent()
    ctx = QuantContext(zscore=2.5, hurst_exponent=0.3)
    opinion = agent.analyze(ctx)
    assert opinion.direction == "SHORT"


def test_trending_regime_follows_autocorrelation_not_zscore():
    agent = QuantAgent()
    # Aşırı oversold z-score ama TRENDING rejimde — mean-reversion bahsi
    # yapılmamalı, momentum'un yönü (pozitif autocorrelation) esas alınmalı.
    ctx = QuantContext(zscore=-2.5, hurst_exponent=0.7, autocorrelation=0.5)
    opinion = agent.analyze(ctx)
    assert opinion.direction == "LONG"
    assert any("momentum" in e.lower() for e in opinion.evidence)


def test_random_walk_regime_has_no_edge():
    agent = QuantAgent()
    ctx = QuantContext(zscore=-2.5, hurst_exponent=0.5)
    opinion = agent.analyze(ctx)
    assert opinion.direction == "WAIT"
    assert any("rastgele yürüyüşe" in c.lower() for c in opinion.caveats)


def test_hurst_dead_zone_never_produces_a_directional_call():
    """Ölü bölgede (0.45-0.55) mean-reverting/trending dallarının ikisi de
    kilitli — Faz 339'da long_term_trend_regime tamamen kaldırıldıktan
    sonra bu bölgede ARTIK HİÇBİR kanıt kaynağı yok, her zaman WAIT."""
    agent = QuantAgent()
    opinion = agent.analyze(QuantContext(hurst_exponent=0.5, zscore=-2.5, autocorrelation=0.5))
    assert opinion.direction == "WAIT"
    assert opinion.feature_contributions == {}


def test_extreme_volatility_dampens_confidence():
    agent = QuantAgent()
    normal_vol = agent.analyze(QuantContext(zscore=-2.5, hurst_exponent=0.3, realized_vol_percentile=50))
    extreme_vol = agent.analyze(QuantContext(zscore=-2.5, hurst_exponent=0.3, realized_vol_percentile=95))
    assert extreme_vol.confidence < normal_vol.confidence


def test_feature_contributions_sum_to_the_implied_raw_score():
    """Faz 268-sonrası: Feature Importance — SHAP gibi bir yaklaşık yöntem
    DEĞİL, bu ajanın skorlaması zaten kesin/katkısal. feature_contributions
    her zaman GERÇEK score'a (confidence = min(|score|/4.0, 0.85)) eşit
    toplanmalı — icat edilmiş/eksik bir katkı dökümü asla üretilmemeli."""
    agent = QuantAgent()
    opinion = agent.analyze(QuantContext(zscore=-2.5, hurst_exponent=0.3))
    implied_score = sum(opinion.feature_contributions.values())
    # confidence = min(|score|/4.0, 0.85) -> |score| = confidence*4.0 (tavana çarpmadığı sürece)
    assert abs(abs(implied_score) - opinion.confidence * 4.0) < 1e-6


def test_feature_contributions_are_empty_when_no_signal_fires():
    agent = QuantAgent()
    opinion = agent.analyze(QuantContext())  # tüm varsayılanlar -> hiçbir dal tetiklenmez
    assert opinion.feature_contributions == {}


def test_feature_contributions_names_the_active_signal():
    agent = QuantAgent()
    opinion = agent.analyze(QuantContext(zscore=-2.5, hurst_exponent=0.3))
    assert "zscore_mean_reversion" in opinion.feature_contributions
    assert opinion.feature_contributions["zscore_mean_reversion"] > 0  # oversold -> LONG bahsi
