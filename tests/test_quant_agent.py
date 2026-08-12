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
    assert any("random walk" in c.lower() for c in opinion.caveats)


def test_hurst_dead_zone_discounts_a_lone_long_term_regime_signal_to_wait():
    """Faz 268e — gerçek bulgu: canlıda SI=F/GC=F/XAUTUSDT'de tekrar eden
    yanlış SHORT'lar bulundu — Hurst ölü bölgesindeyken (0.45-0.55, "ne
    trend ne mean-reversion") TEK kanıt (long_term_trend_regime=bear_trend,
    ham skor -1.0) hiç indirim görmeden confidence=0.25 üretiyordu, sonra
    bu zayıf sinyal kalibrasyonla %77.5'e şişiyordu. Artık ölü bölgede skor
    yarıya iniyor (-0.5) — tek başına bir yön kararı için yetersiz kalıp
    WAIT'e düşüyor, aşırı volatilite indirimiyle AYNI ilke."""
    agent = QuantAgent()
    ctx = QuantContext(zscore=0.0, hurst_exponent=0.47, long_term_trend_regime="bear_trend")
    opinion = agent.analyze(ctx)
    assert opinion.direction == "WAIT"
    assert any("random walk" in c.lower() for c in opinion.caveats)


def test_hurst_dead_zone_never_produces_a_directional_call_on_its_own():
    """Ölü bölgede TEK olası kanıt kaynağı long_term_trend_regime (zscore/
    autocorrelation, mean-reverting/trending dallarının arkasında kilitli
    — ikisi de dead zone'da hiç çalışmıyor). Maksimum ham katkısı 1.0,
    0.5 indirimden sonra 0.5 — yön eşiği (>0.5/<-0.5) TAM bu sınırda,
    asla aşılmıyor. Yani Hurst ölü bölgesi TEK BAŞINA hiçbir zaman yönlü
    bir karara yol açamaz — bu, düzeltmenin kasıtlı, deterministik bir
    sonucu."""
    agent = QuantAgent()
    for regime in ("bull_trend", "bear_trend"):
        opinion = agent.analyze(QuantContext(hurst_exponent=0.5, long_term_trend_regime=regime))
        assert opinion.direction == "WAIT"


def test_extreme_volatility_dampens_confidence():
    agent = QuantAgent()
    normal_vol = agent.analyze(QuantContext(zscore=-2.5, hurst_exponent=0.3, realized_vol_percentile=50))
    extreme_vol = agent.analyze(QuantContext(zscore=-2.5, hurst_exponent=0.3, realized_vol_percentile=95))
    assert extreme_vol.confidence < normal_vol.confidence


def test_regime_changepoint_discounts_the_long_term_trend_signal():
    """Faz 268-sonrası — gerçek olay (2026-08-12): long_term_trend_regime
    yavaş/gecikmeli olduğu için fiyat tersine dönerken bile eski rejimi
    okumaya devam edip 50 ardışık gerçek kayba katkıda bulundu. Gerçek
    bir changepoint tespit edildiğinde bu SPESİFİK sinyalin katkısı
    indirime uğramalı — Hurst tabanlı trend/mean-reversion kanıtı
    ETKİLENMEMELİ (burada autocorrelation=0 ile o katkı zaten sıfır,
    long_term_contribution'ı temiz izole ediyor)."""
    agent = QuantAgent()
    without_changepoint = agent.analyze(QuantContext(
        hurst_exponent=0.6, autocorrelation=0.0,
        long_term_trend_regime="bull_trend", regime_changepoint_detected=False,
    ))
    with_changepoint = agent.analyze(QuantContext(
        hurst_exponent=0.6, autocorrelation=0.0,
        long_term_trend_regime="bull_trend", regime_changepoint_detected=True,
    ))
    assert without_changepoint.direction == "LONG"
    assert with_changepoint.direction == "WAIT"
    assert with_changepoint.confidence < without_changepoint.confidence
    assert any("changepoint" in c.lower() for c in with_changepoint.caveats)


def test_regime_changepoint_has_no_effect_without_a_long_term_regime_signal():
    """long_term_trend_regime hiç yoksa (insufficient_data) indirilecek
    bir katkı da yok — changepoint bayrağı tek başına bir skor
    üretmemeli."""
    agent = QuantAgent()
    opinion = agent.analyze(QuantContext(
        hurst_exponent=0.6, autocorrelation=0.0,
        long_term_trend_regime="insufficient_data", regime_changepoint_detected=True,
    ))
    assert opinion.direction == "WAIT"
    assert not any("changepoint" in c.lower() for c in opinion.caveats)
