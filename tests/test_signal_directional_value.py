"""Faz 460 — analytics/signal_directional_value.py birim testleri.

Üç hükmün (doğru işaret / ters / sinyal yok) ve REJİM EŞDOĞRUSALLIĞI
tespitinin her biri ayrı ayrı sınanıyor. Eşdoğrusallık ayrı bir test
grubunu hak ediyor çünkü 2026-09-09'da gerçek veride bulunan en derin
bulgu oydu: `trend`/`momentum`, `market_regime` ile %100 eşdoğrusaldı --
yani ters bir sinyal değil, başka bir şeyin kopyasıydılar, ve bu iki
teşhis taban tabana zıt düzeltmeler gerektirir.
"""
import math

from analytics.signal_directional_value import compute_signal_directional_value


def _recs(signal, contribution, up_count, down_count, day="2026-09-01", regime=None):
    out = []
    out += [{
        "signal": signal, "contribution": contribution, "forward_label": "UP",
        "day": day, "regime": regime,
    }] * up_count
    out += [{
        "signal": signal, "contribution": contribution, "forward_label": "DOWN",
        "day": day, "regime": regime,
    }] * down_count
    return out


def test_detects_an_inverted_signal():
    """Katkı pozitifken ("yukarı" oyu) fiyat daha AZ yükseliyorsa sinyal
    ters işaretlidir -- gerçek veride trend/momentum/ema_alignment'ın
    durumu."""
    records = _recs("trend", +1.0, up_count=140, down_count=260)
    records += _recs("trend", -1.0, up_count=260, down_count=140)

    result = compute_signal_directional_value(records)
    signal = result["signals"]["trend"]

    assert signal["verdict"] == "inverted"
    assert math.isclose(signal["separation"], 0.35 - 0.65, abs_tol=1e-6)
    assert "trend" in result["inverted_signals"]


def test_detects_a_correctly_signed_signal():
    """rsi_extreme'in gerçek veride ölçülen durumu: pozitif katkı ->
    daha çok yükseliş."""
    records = _recs("rsi_extreme", +1.0, up_count=260, down_count=140)
    records += _recs("rsi_extreme", -1.0, up_count=140, down_count=260)

    result = compute_signal_directional_value(records)

    assert result["signals"]["rsi_extreme"]["verdict"] == "correct_sign"
    assert result["correct_sign_signals"] == ["rsi_extreme"]


def test_signal_inside_the_neutral_band_is_reported_as_no_signal():
    """±0,02 altı gürültüden ayırt edilemez -- "ters" ya da "doğru" diye
    etiketlenmemeli."""
    records = _recs("sentiment_score", +1.0, up_count=201, down_count=199)
    records += _recs("sentiment_score", -1.0, up_count=199, down_count=201)

    result = compute_signal_directional_value(records)

    assert result["signals"]["sentiment_score"]["verdict"] == "no_signal"
    assert result["inverted_signals"] == []
    assert result["correct_sign_signals"] == []


def test_flags_a_signal_that_is_perfectly_collinear_with_regime():
    """EN KRİTİK TEST. Gerçek veride bulunan durum: `trend` bearish
    rejimlerde HER ZAMAN negatif, bullish rejimlerde HER ZAMAN pozitif --
    6.019 gözlemde tek istisna yok. Böyle bir sinyal bağımsız kanıt
    değildir; rejim etiketinin oy olarak yeniden kodlanmış hâlidir.

    Bunu "ters sinyal" diye teşhis edip işaretini çevirmek YANLIŞ
    düzeltme olurdu -- doğru düzeltme redundansı kaldırmak."""
    records = []
    records += _recs("trend", +1.0, 120, 180, regime="bullish_normal")
    records += _recs("trend", +1.0, 110, 190, regime="bullish_low")
    records += _recs("trend", -1.0, 190, 110, regime="bearish_normal")
    records += _recs("trend", -1.0, 180, 120, regime="bearish_low")

    result = compute_signal_directional_value(records)

    assert result["signals"]["trend"]["regime_collinear"] is True
    assert result["signals"]["trend"]["regimes_seen"] == 4
    assert "trend" in result["regime_collinear_signals"]


def test_does_not_flag_collinearity_when_signal_varies_inside_a_regime():
    """rsi_extreme rejim içinde İŞARET DEĞİŞTİRİYOR (aşırı alım/aşırı
    satım) -- yani gerçekten bağımsız bilgi taşıyor. Eşdoğrusal
    işaretlenmemeli."""
    records = []
    for regime in ("bullish_normal", "bearish_normal"):
        records += _recs("rsi_extreme", +1.0, 130, 70, regime=regime)
        records += _recs("rsi_extreme", -1.0, 70, 130, regime=regime)

    result = compute_signal_directional_value(records)

    assert result["signals"]["rsi_extreme"]["regime_collinear"] is False
    assert result["regime_collinear_signals"] == []


def test_collinearity_is_none_when_regime_data_is_missing():
    """Rejim bilgisi yoksa eşdoğrusallık HESAPLANAMAZ -- False (yani
    "temiz") demek uydurma bir güvence olurdu."""
    records = _recs("trend", +1.0, 140, 260)
    records += _recs("trend", -1.0, 260, 140)

    result = compute_signal_directional_value(records)

    assert result["signals"]["trend"]["regime_collinear"] is None
    assert result["regime_collinear_signals"] == []


def test_daily_consistency_is_reported():
    """Örtüşen örneklem itirazına karşı asıl kanıt günlük tutarlılık:
    gerçek veride trend 7/7 günde negatifti."""
    records = []
    for day in ("2026-09-01", "2026-09-02", "2026-09-03"):
        records += _recs("trend", +1.0, 50, 100, day=day)
        records += _recs("trend", -1.0, 100, 50, day=day)

    result = compute_signal_directional_value(records)

    assert result["signals"]["trend"]["daily"]["days"] == 3
    assert result["signals"]["trend"]["daily"]["negative_days"] == 3
    assert result["signals"]["trend"]["daily"]["positive_days"] == 0


def test_thin_signals_are_marked_unusable_not_dropped():
    """Az örnekli bir sinyal sessizce kaybolmamalı -- raporda
    `usable: false` ile görünmeli."""
    records = _recs("wyckoff_event", +1.0, 10, 10)
    records += _recs("wyckoff_event", -1.0, 10, 10)

    result = compute_signal_directional_value(records)

    assert result["signals"]["wyckoff_event"]["usable"] is False
    assert result["signals"]["wyckoff_event"]["separation"] is None


def test_zero_contributions_are_excluded():
    """Katkısı 0 olan sinyal o kararda hiç oy vermemiştir; "aşağı" oyu
    sayılamaz."""
    records = _recs("trend", 0.0, 200, 200)
    assert compute_signal_directional_value(records) is None


def test_one_sided_signal_cannot_be_evaluated():
    """Sadece pozitif katkı veren bir sinyalin separation'ı tanımsızdır
    (karşılaştıracak negatif taraf yok) -- uydurma bir sayı üretilmemeli."""
    records = _recs("always_bullish", +1.0, 300, 300)
    result = compute_signal_directional_value(records)
    assert result["signals"]["always_bullish"]["usable"] is False
