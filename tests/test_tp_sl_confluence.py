"""analytics/tp_sl_confluence.py — Faz 299-300. Kullanıcı isteği
(2026-08-19): TP/SL için çok-yöntemli confluence ("zone of agreement" —
literal ortalama değil, kaç bağımsız yöntemin aynı bölgede birleştiğinin
sayımı)."""
from analytics.tp_sl_confluence import (
    compute_confluence_zones,
    find_nearby_confluence_zone,
    snap_target_to_confluence,
)


def test_compute_confluence_zones_clusters_nearby_levels():
    levels = {
        "sr_resistance": 100.2,
        "volume_profile_poc": 100.4,
        "pivot_r1": 105.0,
    }
    zones = compute_confluence_zones(levels, tolerance_pct=0.005)
    # 100.2/100.4 aynı bölgede (fark %0.2 < %0.5), 105.0 ayrı bir bölge.
    assert len(zones) == 2
    strong = [z for z in zones if z["method_count"] == 2][0]
    assert set(strong["contributing_methods"]) == {"sr_resistance", "volume_profile_poc"}
    assert 100.2 <= strong["level"] <= 100.4


def test_compute_confluence_zones_empty_input_returns_empty_list():
    assert compute_confluence_zones({}) == []


def test_find_nearby_confluence_zone_requires_min_method_count():
    zones = [{"level": 100.0, "method_count": 1, "contributing_methods": ["a"]}]
    assert find_nearby_confluence_zone(100.0, zones, min_method_count=2) is None


def test_find_nearby_confluence_zone_matches_within_tolerance():
    zones = [{"level": 100.0, "method_count": 2, "contributing_methods": ["a", "b"]}]
    result = find_nearby_confluence_zone(100.3, zones, tolerance_pct=0.005)
    assert result is not None
    assert result["level"] == 100.0


def test_find_nearby_confluence_zone_returns_none_for_nonpositive_price():
    zones = [{"level": 100.0, "method_count": 2, "contributing_methods": ["a", "b"]}]
    assert find_nearby_confluence_zone(0.0, zones) is None


def test_snap_target_to_confluence_tightens_long_target_to_zone_in_between():
    """LONG: fiyat 100, ham hedef 110. 105'te 2 yöntemin birleştiği
    gerçek bir direnç var — hedef bu direncin HEMEN ÖNÜNE çekilmeli
    (110'dan UZAK değil, 100-110 arasında, 105'e yakın)."""
    zones = [{"level": 105.0, "method_count": 2, "contributing_methods": ["sr_resistance", "pivot_r1"]}]
    adjusted, used_zone = snap_target_to_confluence("LONG", 100.0, 110.0, zones)
    assert used_zone is not None
    assert 100.0 < adjusted < 105.0  # zone'un hemen altına çekildi, ötesine değil


def test_snap_target_to_confluence_tightens_short_target_to_zone_in_between():
    zones = [{"level": 95.0, "method_count": 2, "contributing_methods": ["sr_support", "volume_profile_poc"]}]
    adjusted, used_zone = snap_target_to_confluence("SHORT", 100.0, 90.0, zones)
    assert used_zone is not None
    assert 95.0 < adjusted < 100.0


def test_snap_target_to_confluence_ignores_zone_beyond_target():
    """Confluence bölgesi hedefin ÖTESİNDEYSE (aradan geçilmesi
    gerekmiyor) hiç kullanılmamalı — hedef asla daha UZAĞA taşınmaz."""
    zones = [{"level": 120.0, "method_count": 2, "contributing_methods": ["a", "b"]}]
    adjusted, used_zone = snap_target_to_confluence("LONG", 100.0, 110.0, zones)
    assert used_zone is None
    assert adjusted == 110.0


def test_snap_target_to_confluence_ignores_weak_zone_below_min_method_count():
    zones = [{"level": 105.0, "method_count": 1, "contributing_methods": ["sr_resistance"]}]
    adjusted, used_zone = snap_target_to_confluence("LONG", 100.0, 110.0, zones)
    assert used_zone is None
    assert adjusted == 110.0


def test_snap_target_to_confluence_fail_closed_with_no_zones():
    adjusted, used_zone = snap_target_to_confluence("LONG", 100.0, 110.0, [])
    assert used_zone is None
    assert adjusted == 110.0


def test_snap_target_to_confluence_picks_nearest_zone_when_multiple_in_range():
    zones = [
        {"level": 108.0, "method_count": 2, "contributing_methods": ["a", "b"]},
        {"level": 103.0, "method_count": 2, "contributing_methods": ["c", "d"]},
    ]
    adjusted, used_zone = snap_target_to_confluence("LONG", 100.0, 110.0, zones)
    assert used_zone["level"] == 103.0  # fiyata daha yakın olan, ilk karşılaşılacak bölge
