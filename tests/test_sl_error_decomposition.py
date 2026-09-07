"""analytics/sl_error_decomposition.py — Faz 443 (2026-09-07), Direction
Prediction Engine, GPT'nin 1 numaralı önceliği: her SL için gerçek yön
hatası mı zamanlama hatası mı ayrımı."""
from analytics.sl_error_decomposition import classify_sl_error, compute_sl_error_decomposition


def test_timing_error_when_mfe_reaches_at_least_half_of_target():
    """Hedef %10 uzakta, MFE %6 -> oran 0.6 >= 0.5 -> timing_error."""
    assert classify_sl_error(mfe_pct=0.06, entry_price=100.0, take_profit_price=110.0) == "timing_error"


def test_genuine_direction_error_when_mfe_barely_moved():
    """Hedef %10 uzakta, MFE %0.5 -> oran 0.05 < 0.1 -> genuine_direction_error."""
    assert classify_sl_error(mfe_pct=0.005, entry_price=100.0, take_profit_price=110.0) == "genuine_direction_error"


def test_partial_move_in_the_middle_band():
    """Hedef %10 uzakta, MFE %2.5 -> oran 0.25, ne net zamanlama ne net yön hatası."""
    assert classify_sl_error(mfe_pct=0.025, entry_price=100.0, take_profit_price=110.0) == "partial_move"


def test_none_when_target_distance_is_degenerate():
    assert classify_sl_error(mfe_pct=0.01, entry_price=100.0, take_profit_price=100.0) is None
    assert classify_sl_error(mfe_pct=0.01, entry_price=0.0, take_profit_price=110.0) is None


def test_none_when_a_required_field_is_missing():
    assert classify_sl_error(mfe_pct=None, entry_price=100.0, take_profit_price=110.0) is None
    assert classify_sl_error(mfe_pct=0.01, entry_price=100.0, take_profit_price=None) is None


def test_boundary_at_exactly_the_timing_threshold_counts_as_timing_error():
    """>= sınırı katı -- tam 0.5 oranı timing_error sayılmalı."""
    assert classify_sl_error(mfe_pct=0.05, entry_price=100.0, take_profit_price=110.0) == "timing_error"


def test_boundary_at_exactly_the_direction_threshold_is_not_direction_error():
    """< sınırı katı -- eşiğin (0.1) hemen ÜSTÜNDEKİ bir oran genuine_
    direction_error SAYILMAMALI (partial_move). Ondalık kesirlerin
    float temsili yüzünden 0.01/0.1 TAM 0.1 vermeyebiliyor (bkz. bir
    önceki test) -- burada eşiği açıkça geçen bir değer kullanılıyor."""
    assert classify_sl_error(mfe_pct=0.0101, entry_price=100.0, take_profit_price=110.0) == "partial_move"


def test_compute_sl_error_decomposition_matches_todays_real_finding_shape():
    """Bugünkü gerçek bulgu: gerçek yön hatası çoğunlukta (~%56-65),
    zamanlama hatası azınlıkta (~%20). Bu test, AYNI büyüklük sırasını
    (genuine_direction_error > timing_error) sentetik veriyle doğruluyor."""
    records = (
        [{"direction": "LONG", "mfe_pct": 0.005, "entry_price": 100.0, "take_profit_price": 110.0} for _ in range(65)]
        + [{"direction": "LONG", "mfe_pct": 0.06, "entry_price": 100.0, "take_profit_price": 110.0} for _ in range(19)]
        + [{"direction": "LONG", "mfe_pct": 0.025, "entry_price": 100.0, "take_profit_price": 110.0} for _ in range(16)]
    )
    result = compute_sl_error_decomposition(records)
    assert result["LONG"]["n"] == 100
    assert result["LONG"]["pct_genuine_direction_error"] == 65.0
    assert result["LONG"]["pct_timing_error"] == 19.0
    assert result["LONG"]["pct_partial_move"] == 16.0
    assert result["LONG"]["pct_genuine_direction_error"] > result["LONG"]["pct_timing_error"]


def test_directions_are_kept_separate():
    records = [
        {"direction": "LONG", "mfe_pct": 0.005, "entry_price": 100.0, "take_profit_price": 110.0},
        {"direction": "SHORT", "mfe_pct": 0.06, "entry_price": 100.0, "take_profit_price": 90.0},
    ]
    result = compute_sl_error_decomposition(records)
    assert set(result.keys()) == {"LONG", "SHORT"}
    assert result["LONG"]["n"] == 1
    assert result["SHORT"]["n"] == 1


def test_records_with_wait_or_missing_direction_are_ignored():
    records = [
        {"direction": "WAIT", "mfe_pct": 0.06, "entry_price": 100.0, "take_profit_price": 110.0},
        {"direction": None, "mfe_pct": 0.06, "entry_price": 100.0, "take_profit_price": 110.0},
    ]
    assert compute_sl_error_decomposition(records) == {}
