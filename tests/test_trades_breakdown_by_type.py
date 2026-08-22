"""GET /api/v1/trades/breakdown-by-type — kullanıcı isteği: "işlem
türüne göre açık pozisyonlar diye bir yer eklemişsin güzel ama kapanmış
işlemlerin olduğu kısıma ratioları eklememişsin oradaki bilgiye de
ihtiyacım var." tests/test_positions_breakdown_by_type.py ile AYNI
desen, sadece status='closed' üzerinde."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from contracts.auth import Role
from contracts.decision_event import DecisionEvent
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from tests.auth_helpers import make_authed_headers


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from api.main import app
    return TestClient(app)


def _open_and_close(symbol: str, direction: str, **kwargs) -> DecisionEvent:
    now = datetime.now(UTC)
    event = DecisionEvent(
        id=uuid4(), timestamp=now, symbol=symbol,
        proposed_direction=direction, final_action=direction, final_size=1.0, confidence=0.7,
        status="open", entry_price=100.0, quantity=1.0, opened_at=now,
        **kwargs,
    )
    with SessionFactory.get_session() as session:
        repo = DecisionPersistor(session)
        repo.persist(event)
        repo.close_position(decision_id=str(event.id), exit_price=101.0, pnl=1.0, closed_at=now)
    return event


def _counts(client) -> dict[tuple[str, str], int]:
    response = client.get("/api/v1/trades/breakdown-by-type", headers=make_authed_headers(Role.VIEWER))
    assert response.status_code == 200
    return {(r["trade_type"], r["direction"]): r["position_count"] for r in response.json()["breakdown"]}


def test_requires_auth(client):
    response = client.get("/api/v1/trades/breakdown-by-type")
    assert response.status_code in (401, 403)


def test_classifies_by_real_stop_distance_regardless_of_timeframe(client):
    """Faz 323 — kullanıcı bulgusu: "orta_vadeli" (timeframe IN ('4h','1d'))
    kovası kaldırıldı — candle_timeframe gibi ilgisiz bir ayara bağımlı,
    kırılgan bir vekildi (6 gün boyunca scalp/swing'i hiç yeni kayıt
    almadan dondurmuştu). timeframe='1d' olsa bile sınıflandırma artık
    SADECE gerçek stop mesafesine bakıyor — burada %2 (< %4.5) -> scalp."""
    before = _counts(client)
    symbol = f"CBRKMT{uuid4().hex[:8]}"
    _open_and_close(symbol, "SHORT", stop_loss_price=102.0, take_profit_price=95.0, timeframe="1d")

    after = _counts(client)
    assert after.get(("scalp", "SHORT"), 0) == before.get(("scalp", "SHORT"), 0) + 1
    assert "orta_vadeli" not in {t for t, _ in after}


def test_excluded_from_stats_trade_is_not_counted_in_breakdown(client):
    """Faz 282 — kritik bulgu: bu agregasyon excluded_from_stats'ı hiç
    kontrol etmiyordu, faz279/280/281'de bilinen bug'lardan kirlenmiş
    diye işaretlenen pump_fade/scalp/hedge satırları hâlâ dashboard'un
    "işlem türüne göre dağılım" tablosunda görünmeye devam ediyordu."""
    from sqlalchemy import text

    before = _counts(client)
    symbol = f"CBRKEXCL{uuid4().hex[:8]}"
    event = _open_and_close(symbol, "SHORT", stop_loss_price=102.0, take_profit_price=95.0)
    with SessionFactory.get_session() as session:
        session.execute(
            text("UPDATE decisions SET excluded_from_stats = true WHERE id = :id"),
            {"id": str(event.id)},
        )
        session.commit()

    after = _counts(client)
    assert after == before


def test_open_position_is_not_counted_in_closed_breakdown(client):
    """Aynı sembolde hem açık hem kapanmış işlem karışmamalı — yeni bir
    açık pozisyon burada hiç sayılmamalı."""
    before = _counts(client)
    symbol = f"CBRKOPEN{uuid4().hex[:8]}"
    now = datetime.now(UTC)
    event = DecisionEvent(
        id=uuid4(), timestamp=now, symbol=symbol,
        proposed_direction="LONG", final_action="LONG", final_size=1.0, confidence=0.7,
        status="open", entry_price=100.0, quantity=1.0, opened_at=now,
        stop_loss_price=98.0, take_profit_price=105.0,
    )
    with SessionFactory.get_session() as session:
        DecisionPersistor(session).persist(event)

    after = _counts(client)
    assert after == before
