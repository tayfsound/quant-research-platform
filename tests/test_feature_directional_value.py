"""Faz 462 — analytics/feature_directional_value.py birim testleri."""
import math

from analytics.feature_directional_value import compute_feature_directional_value


def _num(feature, value, up_n, down_n, day="2026-09-01"):
    return (
        [{"feature": feature, "value": value, "forward_label": "UP", "day": day}] * up_n
        + [{"feature": feature, "value": value, "forward_label": "DOWN", "day": day}] * down_n
    )


def _cat(feature, value, up_n, down_n):
    return _num(feature, value, up_n, down_n)


def test_numeric_feature_positive_separation():
    """Yüksek değerlerde daha çok yükseliş -> doğru işaretli sayısal
    özellik."""
    records = _num("rsi_slope", 10.0, 300, 100) + _num("rsi_slope", -10.0, 100, 300)
    result = compute_feature_directional_value(records)
    f = result["features"]["rsi_slope"]

    assert f["kind"] == "numeric"
    assert f["verdict"] == "correct_sign"
    assert math.isclose(f["separation"], 0.75 - 0.25, abs_tol=1e-6)


def test_numeric_feature_inverted_separation():
    records = _num("momentum", 10.0, 100, 300) + _num("momentum", -10.0, 300, 100)
    result = compute_feature_directional_value(records)
    assert result["features"]["momentum"]["verdict"] == "inverted"


def test_monotonicity_flag_detects_strengthening_at_the_extremes():
    """Faz 461'de taker akışında kullanılan AYNI ölçüt: gerçek bilgi
    uçlarda GÜÇLENİR. Burada en uç %10, çeyrekliklerden daha güçlü bir
    ayrım vermeli."""
    records = []
    # Uc degerler cok guclu, orta degerler zayif.
    records += _num("flow_z", 3.0, 280, 20)
    records += _num("flow_z", 1.0, 160, 140)
    records += _num("flow_z", -1.0, 140, 160)
    records += _num("flow_z", -3.0, 20, 280)

    f = compute_feature_directional_value(records)["features"]["flow_z"]

    assert f["monotonic"] is True
    assert abs(f["extreme_separation"]) > abs(f["separation"])


def test_numeric_feature_inside_neutral_band_is_no_signal():
    records = _num("atr", 10.0, 201, 199) + _num("atr", 1.0, 199, 201)
    assert compute_feature_directional_value(records)["features"]["atr"]["verdict"] == "no_signal"


def test_categorical_feature_reports_discrimination():
    """Faz 436'nın order_flow_relationship'inin gerçek veride ölçülen
    deseni: "bullish" kategorilerinde P(UP) DÜŞÜK, "bearish"te YÜKSEK."""
    records = []
    records += _cat("order_flow_relationship_category", "bullish_new_longs", 120, 180)
    records += _cat("order_flow_relationship_category", "bearish_long_capitulation", 170, 130)
    records += _cat("order_flow_relationship_category", "unclear", 150, 150)

    f = compute_feature_directional_value(records)["features"]["order_flow_relationship_category"]

    assert f["kind"] == "categorical"
    assert f["verdict"] == "discriminative"
    assert f["highest_p_up"]["category"] == "bearish_long_capitulation"
    assert f["lowest_p_up"]["category"] == "bullish_new_longs"
    assert math.isclose(f["separation"], 170/300 - 120/300, abs_tol=1e-6)


def test_categorical_feature_needs_two_eligible_categories():
    """Tek kategorili (ör. hep "unclear") bir alan ayırt edici olamaz."""
    records = _cat("liquidation_pressure_category", "no_data", 300, 300)
    records += _cat("liquidation_pressure_category", "long_squeeze", 5, 5)

    f = compute_feature_directional_value(records)["features"]["liquidation_pressure_category"]

    assert f["usable"] is False
    assert f["separation"] is None
    # Yetersiz kategori yine de RAPORDA gorunmeli, sessizce kaybolmamali.
    assert "long_squeeze" in f["categories"]


def test_booleans_are_treated_as_categorical_not_numeric():
    """`isinstance(True, int)` Python'da True -- ama True/False bir ölçek
    değil, bayraktır. Sayısal muamele çeyreklik hesabını anlamsız
    kılardı."""
    records = _cat("regime_changepoint_detected", True, 100, 200)
    records += _cat("regime_changepoint_detected", False, 200, 100)

    f = compute_feature_directional_value(records)["features"]["regime_changepoint_detected"]
    assert f["kind"] == "categorical"


def test_constant_numeric_feature_fails_closed():
    """Değeri hiç değişmeyen bir özellikte çeyreklik ayrımı tanımsız."""
    records = _num("data_quality_score", 1.0, 300, 300)
    f = compute_feature_directional_value(records)["features"]["data_quality_score"]
    assert f["separation"] is None
    assert f["usable"] is False


def test_thin_numeric_feature_is_marked_unusable():
    records = _num("onchain_solana_tps", 100.0, 50, 50) + _num("onchain_solana_tps", 1.0, 50, 50)
    f = compute_feature_directional_value(records)["features"]["onchain_solana_tps"]
    assert f["usable"] is False
    assert f["verdict"] is None


def test_ranking_orders_by_absolute_strength():
    """Ters işaretli güçlü bir sinyal, zayıf doğru işaretliden DAHA
    önemlidir -- sıralama mutlak değere göre olmalı."""
    records = _num("zayif", 10.0, 210, 190) + _num("zayif", 1.0, 190, 210)
    records += _num("guclu_ters", 10.0, 100, 300) + _num("guclu_ters", 1.0, 300, 100)

    ranked = compute_feature_directional_value(records)["ranked_by_strength"]
    assert ranked[0] == "guclu_ters"


def test_none_values_are_excluded():
    records = _num("rsi_divergence", None, 300, 300)
    assert compute_feature_directional_value(records) is None
