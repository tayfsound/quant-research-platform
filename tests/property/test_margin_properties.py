"""Faz 324 — kullanıcı isteği: "test stratejisi: contract/chaos/
property-based testler." simulator/margin.py::max_safe_leverage — Faz
260'ın gerçek olayı: yüksek kaldıraç + geniş ATR kombinasyonunda
likidasyon fiyatı planlanan stop'tan ÖNCE tetiklenip pozisyon hiç
%5 kaybı görmeden tüm teminatı kaybediyordu. max_safe_leverage bu
sorunu "likidasyon mesafesi her zaman stop mesafesinin en az 1.5 katı"
garantisiyle çözdü — ama şimdiye kadar sadece birkaç elle seçilmiş
senaryoda doğrulandı. Bu dosya AYNI garantiyi geniş, rastgele bir
(entry_price, stop_distance_pct, direction) uzayında sınıyor."""
from hypothesis import given, settings
from hypothesis import strategies as st

from simulator.margin import compute_liquidation_price, max_safe_leverage

_entry_price = st.floats(min_value=0.0001, max_value=1_000_000, allow_nan=False, allow_infinity=False)
# Gerçekçi stop mesafesi aralığı — sistemde fiilen görülen değerlerin
# (bkz. api/rest/positions.py::_SCALP_MAX_STOP_PCT, DEFAULT_MIN_STOP_PCT)
# çok üzerinde, ama max_safe_leverage'in kendi iç formülünün (leverage>1
# gerektiren compute_liquidation_price ile birlikte) hâlâ tanımlı kaldığı
# bir üst sınırla (%30) sınırlı.
_stop_distance_pct = st.floats(min_value=0.0001, max_value=0.30, allow_nan=False, allow_infinity=False)
_direction = st.sampled_from(["LONG", "SHORT"])


@given(entry_price=_entry_price, stop_distance_pct=_stop_distance_pct, direction=_direction)
@settings(max_examples=300)
def test_max_safe_leverage_keeps_liquidation_beyond_stop(entry_price, stop_distance_pct, direction):
    """KRİTİK GÜVENLİK İNVARYANTI (Faz 260'ın gerçek olayının kendisi):
    max_safe_leverage()'in önerdiği kaldıraçla açılan bir pozisyonda,
    likidasyon fiyatı planlanan stop'tan HER ZAMAN daha uzak (daha kötü)
    olmalı — stop, likidasyondan ÖNCE tetiklenmeli, pozisyon asla
    planlanan stop'u hiç görmeden tüm teminatı kaybetmemeli."""
    leverage = max_safe_leverage(stop_distance_pct)
    assert leverage is not None
    assert leverage > 1.0

    liquidation_price = compute_liquidation_price(entry_price, direction, leverage)
    assert liquidation_price is not None

    if direction == "LONG":
        stop_price = entry_price * (1 - stop_distance_pct)
        assert liquidation_price < stop_price
    else:
        stop_price = entry_price * (1 + stop_distance_pct)
        assert liquidation_price > stop_price


@given(stop_distance_pct=_stop_distance_pct)
@settings(max_examples=200)
def test_max_safe_leverage_never_exceeds_exchange_cap(stop_distance_pct):
    leverage = max_safe_leverage(stop_distance_pct)
    assert leverage is not None
    assert leverage <= 125.0


@given(entry_price=_entry_price, leverage=st.floats(min_value=1.01, max_value=125.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=200)
def test_liquidation_price_is_worse_than_entry_in_the_losing_direction(entry_price, leverage):
    """LONG için likidasyon her zaman giriş fiyatının ALTINDA, SHORT için
    her zaman ÜSTÜNDE olmalı — likidasyon tanım gereği kayıp yönünde
    gerçekleşir, asla kâr yönünde değil."""
    long_liq = compute_liquidation_price(entry_price, "LONG", leverage)
    short_liq = compute_liquidation_price(entry_price, "SHORT", leverage)
    assert long_liq < entry_price
    assert short_liq > entry_price


def test_max_safe_leverage_fail_closed_on_invalid_stop_distance():
    assert max_safe_leverage(0.0) is None
    assert max_safe_leverage(-0.01) is None
    assert max_safe_leverage(None) is None


def test_compute_liquidation_price_fail_closed_for_unleveraged_or_spot():
    assert compute_liquidation_price(100.0, "LONG", 1.0) is None
    assert compute_liquidation_price(100.0, "LONG", None) is None
    assert compute_liquidation_price(0.0, "LONG", 5.0) is None
