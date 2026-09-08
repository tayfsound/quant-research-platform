"""analytics/council_analog_agreement.py — Faz 452 (2026-09-08), Faz 447'nin
kullanıcı onaylı ilk (gözlem-only) adımı."""
from analytics.council_analog_agreement import compute_council_vs_analog_agreement


def _analog(domains, regime, direction, reversing="rev", volatility_regime="normal",
            structure_phase="neutral", trade_type="scalp"):
    return {
        "domains": domains, "market_regime": regime, "direction": direction,
        "reversing": reversing, "volatility_regime": volatility_regime,
        "structure_phase": structure_phase, "trade_type": trade_type,
    }


def _record(domains, regime, direction, win, reversing="rev", volatility_regime="normal",
            structure_phase="neutral", trade_type="scalp"):
    return {
        "agreeing_domains": frozenset(domains), "market_regime": regime, "direction": direction,
        "win": win, "reversing": reversing, "volatility_regime": volatility_regime,
        "structure_phase": structure_phase, "trade_type": trade_type,
    }


def test_no_gate_eligible_analogs_is_fail_closed_none():
    holdout = [_record({"technical", "macro"}, "bullish_low", "LONG", True) for _ in range(20)]
    assert compute_council_vs_analog_agreement([], holdout) is None


def test_below_min_holdout_sample_is_fail_closed_none():
    analog = _analog(["technical", "macro"], "bullish_low", "LONG")
    holdout = [_record({"technical", "macro"}, "bullish_low", "LONG", True) for _ in range(5)]
    result = compute_council_vs_analog_agreement([analog], holdout, min_holdout_sample=10)
    assert result is None


def test_endorsed_and_other_groups_split_correctly_and_lift_is_the_difference():
    analog = _analog(["technical", "macro"], "bullish_low", "LONG")
    endorsed = (
        [_record({"technical", "macro"}, "bullish_low", "LONG", True) for _ in range(18)]
        + [_record({"technical", "macro"}, "bullish_low", "LONG", False) for _ in range(2)]
    )  # %90 kazanma
    other = (
        [_record({"quant"}, "bearish_high", "SHORT", True) for _ in range(10)]
        + [_record({"quant"}, "bearish_high", "SHORT", False) for _ in range(10)]
    )  # %50 kazanma
    result = compute_council_vs_analog_agreement([analog], endorsed + other)

    assert result["n_endorsed"] == 20
    assert result["n_other"] == 20
    assert result["endorsed_win_rate"] == 0.9
    assert result["other_win_rate"] == 0.5
    assert result["lift"] == 0.4


def test_a_superset_of_agreeing_domains_still_matches():
    """Bir karar analog'un istediği ikiliden FAZLA ajanla uyuşuyorsa
    (ör. 3 ajan aynı yönde) YİNE de 'endorsed' sayılmalı -- compute_
    historical_analogs()'un kendi ÜST KÜME mantığıyla AYNI ilke."""
    analog = _analog(["technical", "macro"], "bullish_low", "LONG")
    holdout = [
        _record({"technical", "macro", "pattern"}, "bullish_low", "LONG", True)
        for _ in range(15)
    ] + [_record({"quant"}, "bearish_high", "SHORT", False) for _ in range(15)]
    result = compute_council_vs_analog_agreement([analog], holdout)
    assert result["n_endorsed"] == 15
    assert result["endorsed_win_rate"] == 1.0


def test_a_record_missing_one_of_the_six_context_dims_does_not_match():
    """Domain'ler üst küme olsa bile diğer 6 boyuttan biri (ör.
    trade_type) uyuşmuyorsa eşleşme SAYILMAMALI -- 7 boyutun HEPSİ
    aynı anlamda kullanılmalı, kısmi eşleşme icat edilmiş bir onay
    üretmemeli."""
    analog = _analog(["technical", "macro"], "bullish_low", "LONG", trade_type="scalp")
    holdout = (
        [_record({"technical", "macro"}, "bullish_low", "LONG", True, trade_type="swing") for _ in range(15)]
        + [_record({"quant"}, "bearish_high", "SHORT", False) for _ in range(15)]
    )
    result = compute_council_vs_analog_agreement([analog], holdout)
    assert result is None  # trade_type uyusmuyor, hicbiri eslesmedi -> 0 < min_holdout_sample


def test_records_with_missing_win_are_excluded():
    analog = _analog(["technical", "macro"], "bullish_low", "LONG")
    holdout = (
        [_record({"technical", "macro"}, "bullish_low", "LONG", True) for _ in range(12)]
        + [{**_record({"technical", "macro"}, "bullish_low", "LONG", True), "win": None} for _ in range(5)]
    )
    result = compute_council_vs_analog_agreement([analog], holdout)
    assert result["n_endorsed"] == 12
