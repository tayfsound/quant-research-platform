"""GET /api/v1/mae-mfe-confidence — MAE/MFE Bootstrap Güven Aralığı,
Cognitive Core 2.0 (Faz 469-493). Collective Intelligence'tan sonraki,
council'i hiç etkilemeyen Grup B adayı."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from contracts.auth import Role
from contracts.decision_event import DecisionEvent
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from tests.auth_helpers import make_authed_headers


def _client():
    from fastapi.testclient import TestClient

    from api.main import app
    return TestClient(app)


def _persist_closed_trade(
    symbol: str, direction: str, mae_pct: float, mfe_pct: float,
    regime: str, volatility_regime: str, closed_at: datetime,
) -> None:
    with SessionFactory.get_session() as session:
        persistor = DecisionPersistor(session)
        event = DecisionEvent(
            id=uuid4(),
            symbol=symbol,
            proposed_direction=direction,
            final_action=direction,
            final_size=0.1,
            confidence=0.7,
            status="open",
            entry_price=100.0,
            quantity=1.0,
            opened_at=closed_at - timedelta(minutes=10),
            agent_opinions=[],
            market_snapshot={"features": {"long_term_trend_regime": regime, "volatility_regime": volatility_regime}},
        )
        persistor.persist(event)
        persistor.close_position(
            decision_id=str(event.id),
            exit_price=101.0,
            pnl=1.0,
            closed_at=closed_at,
            outcome={
                "mae_pct": mae_pct, "mfe_pct": mfe_pct, "win": mfe_pct > abs(mae_pct),
                "time_to_mae_seconds": 100.0, "time_to_mfe_seconds": 50.0,
            },
        )


def test_mae_mfe_confidence_requires_auth():
    client = _client()
    response = client.get("/api/v1/mae-mfe-confidence/")
    assert response.status_code in (401, 403)


def test_mae_mfe_confidence_returns_real_shape():
    client = _client()
    response = client.get("/api/v1/mae-mfe-confidence/", headers=make_authed_headers(Role.VIEWER))
    assert response.status_code == 200
    result = response.json()["result"]
    assert "point_estimates" in result
    assert "confidence_intervals" in result
    assert "total_trades" in result
    assert result["quantile"] == 0.9


def test_mae_mfe_confidence_learns_a_real_bucket_and_reports_its_ci():
    """compute_conditional_mae_distribution'ın MIN_GROUP_SIZE'ı (20) kadar
    gerçek, tutarlı olmayan (dağılımlı) kapanış üretip bootstrap güven
    aralığının gerçekten o kovayı yakaladığını doğruluyor — sabit bir
    değer değil, gerçek dağılımdan türetilmiş bir aralık."""
    base_time = datetime.now(UTC) + timedelta(days=3653)
    symbol = f"MAECI{uuid4().hex[:8]}"

    try:
        for i in range(20):
            mae = -0.01 - (i % 3) * 0.002  # dağılımlı, sabit değil
            _persist_closed_trade(
                symbol, direction="LONG", mae_pct=mae, mfe_pct=0.03,
                regime="mae_ci_test_regime", volatility_regime="normal",
                closed_at=base_time - timedelta(seconds=i),
            )

        from services.mae_mfe_confidence_gatherer import gather_mae_mfe_confidence
        result = gather_mae_mfe_confidence(window=60)

        key = "direction=LONG|regime=mae_ci_test_regime|volatility_regime=normal"
        assert key in result["confidence_intervals"]
        ci = result["confidence_intervals"][key]
        assert ci["ci_lower"] <= ci["point_estimate"] <= ci["ci_upper"]
        assert ci["sample_size"] == 20
        assert key in result["point_estimates"]
    finally:
        with SessionFactory.get_session() as session:
            from sqlalchemy import text
            session.execute(text("DELETE FROM decisions WHERE symbol = :symbol"), {"symbol": symbol})
            session.commit()


def test_mae_mfe_confidence_reports_requires_auth():
    client = _client()
    response = client.get("/api/v1/mae-mfe-confidence/reports")
    assert response.status_code in (401, 403)


def test_mae_mfe_confidence_reports_returns_saved_snapshots():
    from contracts.mae_mfe_confidence_report import MaeMfeConfidenceReport
    from database.repositories.mae_mfe_confidence_report_repository import (
        MaeMfeConfidenceReportRepository,
    )

    with SessionFactory.get_session() as session:
        report = MaeMfeConfidenceReport(result={"total_trades": 42, "confidence_intervals": {}})
        MaeMfeConfidenceReportRepository(session).save(report)

    client = _client()
    response = client.get(
        "/api/v1/mae-mfe-confidence/reports", params={"limit": 5}, headers=make_authed_headers(Role.VIEWER)
    )
    assert response.status_code == 200
    reports = response.json()["reports"]
    assert any(r["id"] == str(report.id) for r in reports)


def test_refresh_mae_mfe_confidence_report_task_saves_a_snapshot():
    from database.repositories.mae_mfe_confidence_report_repository import (
        MaeMfeConfidenceReportRepository,
    )
    from services.tasks import refresh_mae_mfe_confidence_report_task

    result = refresh_mae_mfe_confidence_report_task()
    assert "total_trades" in result

    with SessionFactory.get_session() as session:
        saved = MaeMfeConfidenceReportRepository(session).get_latest()
    assert saved is not None
    assert saved["id"] == result["id"]
