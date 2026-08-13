"""Faz 294 (Cognitive Core 2.0 / M1): Feature Registry testleri.

En kritik doğrulama: gerçek compute_*_signals fonksiyonlarının GERÇEKTEN
döndürdüğü anahtarların hepsi registry'de var mı — registry icat edilmiş
bir liste DEĞİL, gerçek kod çıktısıyla eşleşmeli."""
from datetime import UTC, datetime, timedelta

from market_data.features.feature_registry import (
    FEATURE_REGISTRY,
    get_feature_spec,
    list_features_by_source,
)
from market_data.features.signal_engine import (
    compute_pattern_signals,
    compute_quant_signals,
    compute_technical_signals,
)
from market_data.ingestion.ohlcv import OHLCV


def _bars(n: int) -> list[OHLCV]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        OHLCV(
            timestamp=base + timedelta(minutes=i),
            open=100.0 + i * 0.1, high=100.5 + i * 0.1, low=99.5 + i * 0.1,
            close=100.0 + i * 0.1 + (0.3 if i % 3 == 0 else -0.1), volume=100.0 + i,
        )
        for i in range(n)
    ]


def test_registry_covers_every_real_technical_signal_key():
    result = compute_technical_signals(_bars(60))
    missing = set(result.keys()) - set(FEATURE_REGISTRY.keys())
    assert missing == set(), f"registry'de eksik teknik feature'lar: {missing}"


def test_registry_covers_every_real_pattern_signal_key():
    result = compute_pattern_signals(_bars(60))
    missing = set(result.keys()) - set(FEATURE_REGISTRY.keys())
    assert missing == set(), f"registry'de eksik pattern feature'ı: {missing}"


def test_registry_covers_every_real_quant_signal_key():
    result = compute_quant_signals(_bars(60))
    missing = set(result.keys()) - set(FEATURE_REGISTRY.keys())
    assert missing == set(), f"registry'de eksik quant feature'ı: {missing}"


def test_get_feature_spec_returns_correct_source_for_a_known_feature():
    spec = get_feature_spec("hurst_exponent")
    assert spec is not None
    assert spec.source_function == "compute_quant_signals"
    assert spec.value_type == "float"


def test_get_feature_spec_returns_none_for_unknown_feature():
    assert get_feature_spec("this_feature_does_not_exist") is None


def test_list_features_by_source_groups_correctly():
    technical = list_features_by_source("compute_technical_signals")
    names = {s.name for s in technical}
    assert "RSI" in names and "macd" in names
    assert "hurst_exponent" not in names


def test_every_registry_entry_has_non_empty_required_fields():
    for spec in FEATURE_REGISTRY.values():
        assert spec.name and spec.source_module and spec.source_function and spec.description
        assert spec.value_type in ("float", "str", "bool")


def test_no_duplicate_feature_names():
    names = [spec.name for spec in FEATURE_REGISTRY.values()]
    assert len(names) == len(set(names))
