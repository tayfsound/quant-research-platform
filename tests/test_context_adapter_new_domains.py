"""ContextAdapter'ın bu turda eklenen 5 yeni to_*() metodu."""
from datetime import datetime, timedelta

from contracts.context import CognitiveCycleContext
from services.context_adapter import ContextAdapter


def test_to_pattern_reads_raw_snapshot():
    ctx = CognitiveCycleContext(market={"raw_snapshot": {"structure_phase": "accumulation"}})
    result = ContextAdapter().to_pattern(ctx)
    assert result.structure_phase == "accumulation"


def test_to_quant_reads_raw_snapshot():
    ctx = CognitiveCycleContext(market={"raw_snapshot": {"zscore": -1.5, "hurst_exponent": 0.3}})
    result = ContextAdapter().to_quant(ctx)
    assert result.zscore == -1.5
    assert result.hurst_exponent == 0.3


def test_to_order_flow_defaults_when_no_db_row_and_no_override():
    ctx = CognitiveCycleContext(market={"symbol": "NEVERINGESTEDXYZ"})
    result = ContextAdapter().to_order_flow(ctx)
    assert result.bid_ask_imbalance == 0.0
    assert result.spread_bps == 0.0


def test_to_order_flow_explicit_override_wins_over_db():
    ctx = CognitiveCycleContext(market={"symbol": "BTCUSDT", "raw_snapshot": {"bid_ask_imbalance": 0.9}})
    result = ContextAdapter().to_order_flow(ctx)
    assert result.bid_ask_imbalance == 0.9


def test_to_time_computes_real_wall_clock_fields():
    ctx = CognitiveCycleContext()
    result = ContextAdapter().to_time(ctx)
    assert result.session in ("asia", "europe", "overlap", "us")
    assert result.day_of_week in (
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
    )
    assert 0 <= result.hours_to_funding <= 8


def test_to_epistemology_full_completeness_when_all_expected_features_present():
    ctx = CognitiveCycleContext(market={
        "features": {"RSI": 50, "ema": 100, "macd": 1, "trend": "bullish", "volatility_regime": "normal"}
    })
    result = ContextAdapter().to_epistemology(ctx)
    assert result.feature_completeness == 1.0
    assert result.known_unknown_count == 0


def test_to_epistemology_partial_completeness_when_features_missing():
    ctx = CognitiveCycleContext(market={"features": {"RSI": 50}})
    result = ContextAdapter().to_epistemology(ctx)
    assert result.feature_completeness == 0.2  # 1/5 expected features present
    assert result.known_unknown_count == 4


def test_to_epistemology_data_age_reflects_ctx_timestamp():
    old_ts = datetime.now() - timedelta(seconds=120)
    ctx = CognitiveCycleContext(timestamp=old_ts)
    result = ContextAdapter().to_epistemology(ctx)
    assert result.data_age_seconds >= 100
