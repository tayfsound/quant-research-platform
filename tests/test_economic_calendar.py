"""Economic Calendar Integration (FOMC/CPI) testleri."""
from datetime import UTC, datetime

from market_data.macro.economic_calendar import compute_event_proximity, get_upcoming_events


def test_upcoming_events_finds_a_real_known_fomc_date():
    # 2026-01-28 gerçek FOMC karar günü (federalreserve.gov'dan doğrulandı).
    as_of = datetime(2026, 1, 27, 12, 0, tzinfo=UTC)
    events = get_upcoming_events(as_of, lookahead_hours=48)
    fomc_events = [e for e in events if e["type"] == "fomc"]
    assert len(fomc_events) == 1
    assert fomc_events[0]["date"] == "2026-01-28"
    assert fomc_events[0]["hours_until"] > 0


def test_upcoming_events_finds_a_real_known_cpi_date():
    # 2026-08-12 gerçek CPI yayın günü.
    as_of = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)
    events = get_upcoming_events(as_of, lookahead_hours=48)
    cpi_events = [e for e in events if e["type"] == "cpi"]
    assert len(cpi_events) == 1
    assert cpi_events[0]["date"] == "2026-08-12"


def test_upcoming_events_excludes_past_dates():
    as_of = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)  # CPI 12 Ağustos'ta geçti
    events = get_upcoming_events(as_of, lookahead_hours=48)
    assert all(e["date"] != "2026-08-12" for e in events)


def test_upcoming_events_excludes_dates_outside_the_lookahead_window():
    as_of = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)  # FOMC 28 Ocak'ta, çok uzak
    events = get_upcoming_events(as_of, lookahead_hours=48)
    assert events == []


def test_events_are_sorted_soonest_first():
    as_of = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    events = get_upcoming_events(as_of, lookahead_hours=24 * 60)
    hours = [e["hours_until"] for e in events]
    assert hours == sorted(hours)


def test_event_proximity_flags_imminent_event_within_window():
    as_of = datetime(2026, 1, 27, 12, 0, tzinfo=UTC)  # FOMC 28 Ocak'a ~30 saat
    result = compute_event_proximity(as_of, high_impact_window_hours=48)
    assert result["high_impact_event_imminent"] is True
    assert len(result["next_events"]) >= 1


def test_event_proximity_is_false_with_no_events_in_window():
    as_of = datetime(2026, 2, 1, 0, 0, tzinfo=UTC)  # sonraki FOMC 18 Mart'ta, çok uzak
    result = compute_event_proximity(as_of, high_impact_window_hours=24)
    assert result["high_impact_event_imminent"] is False
    assert result["next_events"] == []
