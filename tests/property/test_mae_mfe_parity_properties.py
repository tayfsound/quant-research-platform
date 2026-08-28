"""Faz 368 — GPT dış rapor önerisi (kullanıcı isteği: "derin doğrulama
testleri"): LONG/SHORT parity testi. analytics/mae_mfe.py::compute_mae_mfe
şu ana kadar SADECE elle seçilmiş örneklerle test edildi — bu dosya,
AYNI (entry_price, bars) girdisi için LONG ve SHORT yönlerinin
matematiksel olarak birbirinin AYNASI olması gerektiği invaryantını
hypothesis ile geniş, rastgele bir girdi uzayında kanıtlıyor.

Kod incelemesiyle türetilen invaryant (compute_mae_mfe'nin kendi
formülünden): SHORT'un adverse_pct(bar)'ı = -LONG'un favorable_pct(bar)'ı,
SHORT'un favorable_pct(bar)'ı = -LONG'un adverse_pct(bar)'ı — HER bar için
birebir. Dolayısıyla:
    SHORT.mae_pct == -LONG.mfe_pct
    SHORT.mfe_pct == -LONG.mae_pct
    SHORT.time_to_mfe == LONG.time_to_mae  (AYNI bar'da gerçekleşir)
    SHORT.time_to_mae == LONG.time_to_mfe

Bu invaryant bir sign/inversion bug'ını (GPT raporunun özellikle
şüphelendiği sınıf) anında yakalar — sistemde bugüne kadar böyle bir
bug bulunmadı, ama bu test onu KALICI olarak imkansız kılıyor."""
from datetime import UTC, datetime, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from analytics.mae_mfe import compute_mae_mfe
from market_data.ingestion.ohlcv import OHLCV

_entry_price = st.floats(min_value=0.01, max_value=100_000, allow_nan=False, allow_infinity=False)


@st.composite
def _bar_sequence(draw):
    n = draw(st.integers(min_value=1, max_value=30))
    bars = []
    base_time = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(n):
        low = draw(st.floats(min_value=0.01, max_value=100_000, allow_nan=False, allow_infinity=False))
        high_extra = draw(st.floats(min_value=0.0, max_value=100_000, allow_nan=False, allow_infinity=False))
        high = low + high_extra
        bars.append(OHLCV(
            timestamp=base_time + timedelta(minutes=i),
            open=low, high=high, low=low, close=low, volume=1.0,
        ))
    return bars


@given(entry_price=_entry_price, bars=_bar_sequence())
@settings(max_examples=300)
def test_short_mae_mirrors_long_mfe(entry_price, bars):
    long_result = compute_mae_mfe("LONG", entry_price, bars)
    short_result = compute_mae_mfe("SHORT", entry_price, bars)

    assert abs(short_result["mae_pct"] - (-long_result["mfe_pct"])) < 1e-9


@given(entry_price=_entry_price, bars=_bar_sequence())
@settings(max_examples=300)
def test_short_mfe_mirrors_long_mae(entry_price, bars):
    long_result = compute_mae_mfe("LONG", entry_price, bars)
    short_result = compute_mae_mfe("SHORT", entry_price, bars)

    assert abs(short_result["mfe_pct"] - (-long_result["mae_pct"])) < 1e-9


@given(entry_price=_entry_price, bars=_bar_sequence())
@settings(max_examples=300)
def test_short_time_to_mfe_matches_long_time_to_mae(entry_price, bars):
    """SHORT'un en iyi anı (mfe), LONG'un en kötü anıyla (mae) AYNI bar'da
    gerçekleşmeli — ikisi de aynı fiziksel olayın (fiyatın en düşük
    noktaya indiği an) iki farklı yönden okunuşu."""
    long_result = compute_mae_mfe("LONG", entry_price, bars)
    short_result = compute_mae_mfe("SHORT", entry_price, bars)

    assert short_result["time_to_mfe_seconds"] == long_result["time_to_mae_seconds"]


@given(entry_price=_entry_price, bars=_bar_sequence())
@settings(max_examples=300)
def test_short_time_to_mae_matches_long_time_to_mfe(entry_price, bars):
    long_result = compute_mae_mfe("LONG", entry_price, bars)
    short_result = compute_mae_mfe("SHORT", entry_price, bars)

    assert short_result["time_to_mae_seconds"] == long_result["time_to_mfe_seconds"]


@given(entry_price=_entry_price, bars=_bar_sequence())
@settings(max_examples=300)
def test_mae_is_never_positive_and_mfe_is_never_negative(entry_price, bars):
    """Sözleşme (compute_mae_mfe'nin kendi docstring'i): mae_pct her zaman
    pozisyon ALEYHİNE (<=0), mfe_pct her zaman pozisyon LEHİNE (>=0) —
    yön ne olursa olsun."""
    for direction in ("LONG", "SHORT"):
        result = compute_mae_mfe(direction, entry_price, bars)
        assert result["mae_pct"] <= 1e-12
        assert result["mfe_pct"] >= -1e-12
