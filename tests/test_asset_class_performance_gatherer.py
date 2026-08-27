"""services/asset_class_performance_gatherer.py::_is_production_ai_council
— kullanıcı bulgusu (2026-08-27): "Kripto" kartının -$84,878 görünen
toplam PNL'i pump_fade_v1'den değil multi_timeframe_cascade_v1 (A/B
deneyi, hem control hem treatment) sızıntısındandı. Bu izolasyonu hem
asset_class_performance_gatherer.py hem regime_performance_gatherer.py
hem market_world_model_gatherer.py PAYLAŞIYOR — testler ortak
davranışı burada doğruluyor."""
from services.asset_class_performance_gatherer import (
    BASIS_ARB_EXPERIMENT_BUCKET,
    MULTI_TIMEFRAME_CASCADE_PREFIX,
    _is_production_ai_council,
)


def test_none_experiment_bucket_is_production():
    assert _is_production_ai_council(None) is True


def test_basis_arb_v1_is_excluded():
    assert _is_production_ai_council(BASIS_ARB_EXPERIMENT_BUCKET) is False


def test_multi_timeframe_cascade_control_and_treatment_are_excluded():
    assert _is_production_ai_council(f"{MULTI_TIMEFRAME_CASCADE_PREFIX}:control") is False
    assert _is_production_ai_council(f"{MULTI_TIMEFRAME_CASCADE_PREFIX}:treatment") is False


def test_other_experiment_buckets_are_not_excluded():
    assert _is_production_ai_council("some_other_experiment_v1") is True
