"""Faz 401 — MarketStateReportRepository gerçek DB entegrasyon testleri.
database/repositories/historical_analog_report_repository.py'nin AYNI
test deseni."""
from contracts.market_state_report import MarketStateReport
from database.repositories.market_state_report_repository import (
    MarketStateReportModel,
    MarketStateReportRepository,
)
from database.session_factory import SessionFactory


def _cleanup(report_id) -> None:
    with SessionFactory.get_session() as session:
        session.query(MarketStateReportModel).filter_by(id=report_id).delete()
        session.commit()


def test_save_and_get_latest_round_trips_real_data():
    report = MarketStateReport(result={"by_symbol": {"BTCUSDT": {"direction": "LONG", "confidence": 0.6}}})
    with SessionFactory.get_session() as session:
        MarketStateReportRepository(session).save(report)
    try:
        with SessionFactory.get_session() as session:
            latest = MarketStateReportRepository(session).get_latest()
        assert latest is not None
        assert latest["id"] == str(report.id)
        assert latest["result"]["by_symbol"]["BTCUSDT"]["direction"] == "LONG"
    finally:
        _cleanup(report.id)


def test_get_latest_returns_the_most_recently_created_report():
    from datetime import UTC, datetime, timedelta

    older = MarketStateReport(
        created_at=datetime.now(UTC) - timedelta(days=1), result={"by_symbol": {"AAA": {"direction": "SHORT"}}},
    )
    newer = MarketStateReport(created_at=datetime.now(UTC), result={"by_symbol": {"BBB": {"direction": "LONG"}}})
    with SessionFactory.get_session() as session:
        repo = MarketStateReportRepository(session)
        repo.save(older)
        repo.save(newer)
    try:
        with SessionFactory.get_session() as session:
            latest = MarketStateReportRepository(session).get_latest()
        assert latest["id"] == str(newer.id)
    finally:
        _cleanup(older.id)
        _cleanup(newer.id)
