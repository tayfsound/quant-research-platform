"""Faz 407 — refresh_market_state_cluster_task artık İKİ ayrı rapor
kaydediyor: market_state_snapshots (by_symbol/n_symbols) VE
correlation_snapshots (pairs, gözlem-only stabilite). tests/
test_agent_combination_reliability_wiring.py'deki AYNI desen."""
from unittest.mock import patch


def test_refresh_market_state_cluster_task_saves_both_reports():
    from database.repositories.correlation_report_repository import CorrelationReportRepository
    from database.repositories.market_state_report_repository import MarketStateReportRepository
    from database.session_factory import SessionFactory
    from services.tasks import refresh_market_state_cluster_task

    fake_result = {
        "by_symbol": {"BTCUSDT": {"direction": "LONG", "confidence": 0.6}},
        "n_symbols": 1,
        "correlation_pairs": [
            {"pair": "BTCUSDT|ETHUSDT", "correlation": 0.85, "correlation_stability": None},
        ],
    }
    with patch("services.market_state_gatherer.gather_market_state_cluster", return_value=fake_result):
        result = refresh_market_state_cluster_task()

    assert result["n_symbols"] == 1
    assert result["correlation_pair_count"] == 1

    with SessionFactory.get_session() as session:
        market_state = MarketStateReportRepository(session).get_latest()
        correlation = CorrelationReportRepository(session).get_latest()

    # market_state raporu correlation_pairs'i İÇERMEMELİ (ayrı rapora taşındı).
    assert "correlation_pairs" not in market_state["result"]
    assert market_state["result"]["by_symbol"]["BTCUSDT"]["direction"] == "LONG"

    assert correlation["id"] == result["correlation_report_id"]
    assert correlation["result"]["pairs"][0]["pair"] == "BTCUSDT|ETHUSDT"
