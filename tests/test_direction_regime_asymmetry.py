"""analytics/direction_regime_asymmetry.py — Faz 364-devam, kullanıcı
hipotezi: bir rejimde SHORT başarısızsa, aynı rejimde LONG başarılı mı."""
from analytics.direction_regime_asymmetry import compute_direction_regime_asymmetry


def _cell(win_rate: float, n: int) -> dict:
    return {"sample_size": n, "win_rate": win_rate, "win_rate_ci": None, "delta_vs_overall": None}


def test_pairs_matching_long_short_labels_and_computes_delta():
    by_strategy = {
        "ai_council_LONG_swing": {
            "overall_win_rate": 0.87, "overall_sample_size": 100,
            "by_regime": {"bearish_low": _cell(0.86, 50)},
        },
        "ai_council_SHORT_swing": {
            "overall_win_rate": 0.09, "overall_sample_size": 100,
            "by_regime": {"bearish_low": _cell(0.05, 40)},
        },
    }
    result = compute_direction_regime_asymmetry(by_strategy)
    assert "ai_council_swing" in result
    cell = result["ai_council_swing"]["by_regime"]["bearish_low"]
    assert cell["long_win_rate"] == 0.86
    assert cell["short_win_rate"] == 0.05
    assert cell["delta_long_minus_short"] == 0.81


def test_only_shared_regimes_are_compared():
    by_strategy = {
        "ai_council_LONG_swing": {
            "overall_win_rate": 0.8, "overall_sample_size": 10,
            "by_regime": {"bearish_low": _cell(0.8, 10), "bullish_high": _cell(0.6, 10)},
        },
        "ai_council_SHORT_swing": {
            "overall_win_rate": 0.1, "overall_sample_size": 10,
            "by_regime": {"bearish_low": _cell(0.1, 10)},
        },
    }
    result = compute_direction_regime_asymmetry(by_strategy)
    assert set(result["ai_council_swing"]["by_regime"].keys()) == {"bearish_low"}


def test_unpaired_direction_is_excluded():
    by_strategy = {
        "pump_fade_SHORT": {
            "overall_win_rate": 0.5, "overall_sample_size": 10,
            "by_regime": {"bearish_low": _cell(0.5, 10)},
        },
    }
    result = compute_direction_regime_asymmetry(by_strategy)
    assert result == {}


def test_empty_input_is_fail_closed():
    assert compute_direction_regime_asymmetry({}) == {}
