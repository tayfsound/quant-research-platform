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
    assert any("rastgele yürüyüşe" in c.lower() for c in opinion.caveats)


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


def test_feature_contributions_sum_to_the_implied_raw_score():
    """Faz 268-sonrası: Feature Importance — SHAP gibi bir yaklaşık yöntem
    DEĞİL, bu ajanın skorlaması zaten kesin/katkısal. feature_contributions
    her zaman GERÇEK score'a (confidence = min(|score|/4.0, 0.85)) eşit
    toplanmalı — icat edilmiş/eksik bir katkı dökümü asla üretilmemeli.

    long_term_trend_regime="insufficient_data" KASITLI — Faz 317-sonrası
    trend-uyum indirimi (bkz. _TREND_AGREEMENT_CONFIDENCE_DISCOUNT) bu
    testin izole etmeye çalıştığı score->confidence ilişkisini bozar,
    ayrı bir test (test_trend_agreement_discounts_confidence_but_keeps_
    feature_contributions_at_raw_score) onu zaten kapsıyor."""
    agent = QuantAgent()
    opinion = agent.analyze(QuantContext(
        zscore=-2.5, hurst_exponent=0.3, long_term_trend_regime="insufficient_data",
    ))
    implied_score = sum(opinion.feature_contributions.values())
    # confidence = min(|score|/4.0, 0.85) -> |score| = confidence*4.0 (tavana çarpmadığı sürece)
    assert abs(abs(implied_score) - opinion.confidence * 4.0) < 1e-6


def test_feature_contributions_are_empty_when_no_signal_fires():
    agent = QuantAgent()
    opinion = agent.analyze(QuantContext())  # tüm varsayılanlar -> hiçbir dal tetiklenmez
    assert opinion.feature_contributions == {}


def test_feature_contributions_names_the_active_signals():
    agent = QuantAgent()
    opinion = agent.analyze(QuantContext(
        zscore=-2.5, hurst_exponent=0.3, long_term_trend_regime="bear_trend",
    ))
    assert "zscore_mean_reversion" in opinion.feature_contributions
    assert "long_term_trend_regime" in opinion.feature_contributions
    assert opinion.feature_contributions["zscore_mean_reversion"] > 0  # oversold -> LONG bahsi
    assert opinion.feature_contributions["long_term_trend_regime"] < 0  # bear_trend -> negatif katkı


def test_feature_contributions_reflect_the_changepoint_discount():
    agent = QuantAgent()
    opinion = agent.analyze(QuantContext(
        hurst_exponent=0.6, autocorrelation=0.0,
        long_term_trend_regime="bull_trend", regime_changepoint_detected=True,
    ))
    assert abs(opinion.feature_contributions["long_term_trend_regime"] - 0.3) < 1e-6


def test_trend_agreement_discounts_confidence_when_direction_matches_long_term_regime():
    """Faz 317-sonrası — kullanıcı bulgusu: "Quant ajanın isabeti sıfıra
    indi." Gerçek geçmiş veri (1333 kapanmış işlem) ölçüldü: yön
    long_term_trend_regime ile AYNI tarafta olduğunda ("agree") kazanma
    oranı sadece %27.9 (n=308) — confidence indirilmeli, direction ASLA
    değişmemeli."""
    agent = QuantAgent()
    # zscore=-2.5 + hurst=0.3 (mean-reverting) -> LONG bahsi (+2.0).
    # long_term_trend_regime=bull_trend -> AYNI taraf (LONG), +1.0.
    agreeing = agent.analyze(QuantContext(
        zscore=-2.5, hurst_exponent=0.3, long_term_trend_regime="bull_trend",
    ))
    baseline = agent.analyze(QuantContext(
        zscore=-2.5, hurst_exponent=0.3, long_term_trend_regime="insufficient_data",
    ))
    assert agreeing.direction == "LONG"
    assert baseline.direction == "LONG"
    # baseline: score=2.0 -> confidence=0.5. agreeing: score=3.0 (2.0+1.0)
    # -> ham confidence=0.75, indirimden sonra 0.75*0.6=0.45 — baseline'dan
    # (0.5) bile DAHA DÜŞÜK, ham skor daha yüksek olmasına rağmen.
    assert agreeing.confidence < baseline.confidence
    assert any("uzun vadeli rejimle" in c.lower() for c in agreeing.caveats)


def test_trend_disagreement_never_changes_confidence_insufficient_evidence():
    """AYNI ölçümde "disagree" kovası sadece n=7 — istatistiksel olarak
    güvenilmez, kalıcı bir ayarlama YAPILMAMALI (ne indirim ne artırım)."""
    agent = QuantAgent()
    # zscore=-2.5 + hurst=0.3 -> LONG bahsi (+2.0). long_term_trend_regime
    # =bear_trend -> TERS taraf (LONG vs bear_trend), -1.0. score=1.0.
    disagreeing = agent.analyze(QuantContext(
        zscore=-2.5, hurst_exponent=0.3, long_term_trend_regime="bear_trend",
    ))
    assert disagreeing.direction == "LONG"
    # confidence = min(1.0/4.0, 0.85) = 0.25 — HİÇ ayarlama yok.
    assert abs(disagreeing.confidence - 0.25) < 1e-9
    assert not any("uzun vadeli rejimle" in c.lower() for c in disagreeing.caveats)


def test_trend_agreement_discount_never_fires_on_wait():
    agent = QuantAgent()
    opinion = agent.analyze(QuantContext(hurst_exponent=0.5, long_term_trend_regime="bull_trend"))
    assert opinion.direction == "WAIT"
    assert not any("uzun vadeli rejimle" in c.lower() for c in opinion.caveats)


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
