"""GET /api/v1/positions/breakdown-by-type — kullanıcı isteği: "scalp,
orta vade vs. farklı işlem türlerinin ne kadarı short ne kadarı
long pozisyonmuş, dashboard'da bir tabloda göreyim." Bu testler, SQL
agregasyonunun api/rest/positions.py::_classify_trade_type() ile AYNI
önceliklendirme sırasını (pump_fade > hedge > scalp/swing — Faz 317'de
"gün içi", Faz 323'te "orta_vadeli" ara kovaları kaldırıldı) uyguladığını,
gerçek verilerle önce/sonra farkı üzerinden doğruluyor — paylaşılan dev
DB'deki ambient veriden etkilenmez."""
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


def _open(symbol: str, direction: str, **kwargs) -> DecisionEvent:
    now = datetime.now(UTC)
    event = DecisionEvent(
        id=uuid4(), timestamp=now, symbol=symbol,
        proposed_direction=direction, final_action=direction, final_size=1.0, confidence=0.7,
        status="open", entry_price=100.0, quantity=1.0, opened_at=now,
        **kwargs,
    )
    with SessionFactory.get_session() as session:
        DecisionPersistor(session).persist(event)
    return event


def _counts(client) -> dict[tuple[str, str], int]:
    response = client.get("/api/v1/positions/breakdown-by-type", headers=make_authed_headers(Role.VIEWER))
    assert response.status_code == 200
    return {(r["trade_type"], r["direction"]): r["position_count"] for r in response.json()["breakdown"]}


def test_requires_auth(client):
    response = client.get("/api/v1/positions/breakdown-by-type")
    assert response.status_code in (401, 403)


def test_classifies_pump_fade_before_stop_distance_heuristic(client):
    before = _counts(client)
    symbol = f"BRKPF{uuid4().hex[:8]}"
    # Stop mesafesi kasıtlı olarak scalp aralığında (%2) — pump_fade
    # etiketinin ondan ÖNCE geldiğini kanıtlamak için.
    _open(symbol, "SHORT", stop_loss_price=102.0, take_profit_price=95.0, experiment_bucket="pump_fade_v1")

    after = _counts(client)
    assert after.get(("pump_fade", "SHORT"), 0) == before.get(("pump_fade", "SHORT"), 0) + 1


def test_timeframe_no_longer_affects_classification(client):
    """Faz 323 — kullanıcı bulgusu: "orta_vadeli" (timeframe IN ('4h','1d'))
    kovası kaldırıldı — candle_timeframe gibi ilgisiz bir ayara bağımlı,
    kırılgan bir vekildi (6 gün boyunca scalp/swing'i hiç yeni kayıt
    almadan dondurmuştu). timeframe='4h' olsa bile sınıflandırma artık
    SADECE gerçek stop mesafesine bakıyor — burada %2 (< %4.5) -> scalp."""
    before = _counts(client)
    symbol = f"BRKMT{uuid4().hex[:8]}"
    _open(symbol, "LONG", stop_loss_price=98.0, take_profit_price=105.0, timeframe="4h")

    after = _counts(client)
    assert after.get(("scalp", "LONG"), 0) == before.get(("scalp", "LONG"), 0) + 1
    assert "orta_vadeli" not in {t for t, _ in after}


def test_classifies_scalp_and_swing_by_stop_distance(client):
    """Faz 317 — "gün içi" ara kovası kaldırıldı (kullanıcı: eski/kirli
    test verisiydi, %70'i manual_full, tek bir yeni işlem yok). %4.5
    üzerindeki her stop mesafesi artık doğrudan swing."""
    before = _counts(client)
    scalp_symbol = f"BRKSC{uuid4().hex[:8]}"
    mid_range_symbol = f"BRKMR{uuid4().hex[:8]}"
    swing_symbol = f"BRKSW{uuid4().hex[:8]}"

    _open(scalp_symbol, "LONG", stop_loss_price=98.0, take_profit_price=105.0)  # %2 -> scalp
    _open(mid_range_symbol, "LONG", stop_loss_price=94.0, take_profit_price=110.0)  # %6 -> swing (eski "gün içi")
    _open(swing_symbol, "SHORT", stop_loss_price=112.0, take_profit_price=80.0)  # %12 -> swing

    after = _counts(client)
    assert after.get(("scalp", "LONG"), 0) == before.get(("scalp", "LONG"), 0) + 1
    assert after.get(("swing", "LONG"), 0) == before.get(("swing", "LONG"), 0) + 1
    assert after.get(("swing", "SHORT"), 0) == before.get(("swing", "SHORT"), 0) + 1
    assert "gun_ici" not in {t for t, _ in after}


def test_excluded_from_stats_position_is_not_counted_in_breakdown(client):
    """Faz 282 — kritik bulgu: bu agregasyon excluded_from_stats'ı hiç
    kontrol etmiyordu, faz279/280/281'de bilinen bug'lardan kirlenmiş
    diye işaretlenen pump_fade/scalp/hedge satırları hâlâ dashboard'un
    "işlem türüne göre dağılım" tablosunda görünmeye devam ediyordu."""
    from sqlalchemy import text

    before = _counts(client)
    symbol = f"BRKEXCL{uuid4().hex[:8]}"
    event = _open(symbol, "LONG", stop_loss_price=98.0, take_profit_price=105.0)
    with SessionFactory.get_session() as session:
        session.execute(
            text("UPDATE decisions SET excluded_from_stats = true WHERE id = :id"),
            {"id": str(event.id)},
        )
        session.commit()

    after = _counts(client)
    assert after == before


def test_position_without_stop_or_timeframe_is_excluded_not_miscategorized(client):
    """entry_price/stop_loss_price yoksa (ve orta-vadeli/pump_fade da
    değilse) NULL trade_type üretir — bu satırlar toplamda YOK sayılır,
    icat edilmiş bir kategoriye düşmez."""
    before_total = sum(_counts(client).values())
    symbol = f"BRKNULL{uuid4().hex[:8]}"
    _open(symbol, "LONG", stop_loss_price=None, take_profit_price=None)

    after_total = sum(_counts(client).values())
    assert after_total == before_total
