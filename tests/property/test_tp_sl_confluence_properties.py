"""Faz 324 — kullanıcı isteği: "test stratejisi: contract/chaos/
property-based testler." analytics/tp_sl_confluence.py::snap_stop_to_
confluence/snap_target_to_confluence şu ana kadar SADECE elle seçilmiş
örneklerle (tests/test_tp_sl_confluence.py, tests/test_risk_target_
stage.py) test edildi — bu dosya AYNI "asla riski artırma" garantisini
hypothesis ile geniş, rastgele bir girdi uzayında (yüzlerce senaryo,
her çalıştırmada farklı) kanıtlıyor. En kritik invaryant: snap_stop_to_
confluence'ın sonucu, seçilen zone ne olursa olsun, orijinal (ham
ATR-tabanlı) stop'tan ASLA fiyata daha UZAK olamaz — dosyanın kendi
docstring'i bunu "yapı gereği kesin" diye tanımlıyor, bu testler o
iddiayı gerçekten sınıyor."""
from hypothesis import given, settings
from hypothesis import strategies as st

from analytics.tp_sl_confluence import snap_stop_to_confluence, snap_target_to_confluence

_price = st.floats(min_value=0.0001, max_value=1_000_000, allow_nan=False, allow_infinity=False)
_pct = st.floats(min_value=0.0001, max_value=2.0, allow_nan=False, allow_infinity=False)
_direction = st.sampled_from(["LONG", "SHORT"])
_method_count = st.integers(min_value=0, max_value=10)


@st.composite
def _zone(draw):
    level = draw(_price)
    method_count = draw(_method_count)
    return {"level": level, "method_count": method_count, "contributing_methods": ["m"] * method_count}


_zones = st.lists(_zone(), min_size=0, max_size=12)


@given(current_price=_price, raw_pct=_pct, direction=_direction, zones=_zones)
@settings(max_examples=300)
def test_snap_stop_never_moves_stop_further_from_price_than_raw(current_price, raw_pct, direction, zones):
    """KRİTİK GÜVENLİK İNVARYANTI: hangi confluence zone'u seçilirse
    seçilsin (ya da hiç seçilmese de), stop'un fiyata olan mesafesi
    ham (icat edilmemiş) ATR-tabanlı stop mesafesini asla AŞAMAZ."""
    raw_stop_price = current_price * (1 - raw_pct) if direction == "LONG" else current_price * (1 + raw_pct)
    adjusted, _used_zone = snap_stop_to_confluence(direction, current_price, raw_stop_price, zones)

    raw_distance = abs(raw_stop_price - current_price)
    adjusted_distance = abs(adjusted - current_price)
    assert adjusted_distance <= raw_distance + 1e-6


@given(current_price=_price, raw_pct=_pct, direction=_direction, zones=_zones)
@settings(max_examples=300)
def test_snap_target_never_moves_target_further_from_price_than_raw(current_price, raw_pct, direction, zones):
    """AYNI "sadece sıkılaştırır" garantisi — hedef için."""
    raw_target_price = current_price * (1 + raw_pct) if direction == "LONG" else current_price * (1 - raw_pct)
    adjusted, _used_zone = snap_target_to_confluence(direction, current_price, raw_target_price, zones)

    raw_distance = abs(raw_target_price - current_price)
    adjusted_distance = abs(adjusted - current_price)
    assert adjusted_distance <= raw_distance + 1e-6


@given(current_price=_price, raw_pct=_pct, direction=_direction, zones=_zones)
@settings(max_examples=300)
def test_snap_stop_used_zone_always_meets_min_method_count(current_price, raw_pct, direction, zones):
    """Döndürülen zone (None değilse) her zaman min_method_count (varsayılan
    2) eşiğini karşılamalı — tek yöntemlik zayıf bir zone'a asla snap
    edilmemeli."""
    raw_stop_price = current_price * (1 - raw_pct) if direction == "LONG" else current_price * (1 + raw_pct)
    _adjusted, used_zone = snap_stop_to_confluence(direction, current_price, raw_stop_price, zones)
    if used_zone is not None:
        assert used_zone["method_count"] >= 2


@given(target_price=_price, direction=_direction, zones=_zones)
@settings(max_examples=100)
def test_snap_target_fail_closed_on_nonpositive_price(target_price, direction, zones):
    adjusted, used_zone = snap_target_to_confluence(direction, 0.0, target_price, zones)
    assert adjusted == target_price
    assert used_zone is None


@given(stop_price=_price, direction=_direction, zones=_zones)
@settings(max_examples=100)
def test_snap_stop_fail_closed_on_nonpositive_price(stop_price, direction, zones):
    adjusted, used_zone = snap_stop_to_confluence(direction, 0.0, stop_price, zones)
    assert adjusted == stop_price
    assert used_zone is None


@given(current_price=_price, target_price=_price, direction=_direction)
@settings(max_examples=100)
def test_snap_target_passthrough_with_no_zones(current_price, target_price, direction):
    adjusted, used_zone = snap_target_to_confluence(direction, current_price, target_price, [])
    assert adjusted == target_price
    assert used_zone is None
