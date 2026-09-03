"""Kullanıcı bulgusu: "Pump-Fade ile açtığı işlem var mı Transactions'ta
göremedim." Kök neden: pump_fade_strategy.py işlemleri experiment_bucket=
"pump_fade_v1" ile etiketliyordu ama api/rest/positions.py bu sütunu hiç
okumuyordu — pump-fade işlemleri stop-mesafesi sezgiselliğine (scalp/gün
içi/swing) düşüp normal AI işlemlerinden ayırt edilemiyordu. Bu testler
GET /positions'ın (açık pozisyonlar) trade_type="pump_fade" döndürdüğünü
ve bunun stop-mesafesi tabanlı sınıflandırmadan ÖNCE geldiğini doğruluyor.

2026-08-29 — "dashboard contamination" düzeltmesi sonrası GET /trades
(kapalı işlemler) artık pump_fade_v1'i BİLİNÇLİ OLARAK hariç tutuyor
(exclude_experiment_bucket) — bu dosyadaki ilgili test buna göre
güncellendi (INCLUDE değil EXCLUDE doğrulanıyor)."""
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


def _open_pump_fade_position(symbol: str):
    now = datetime.now(UTC)
    event = DecisionEvent(
        id=uuid4(), timestamp=now, symbol=symbol,
        proposed_direction="SHORT", final_action="SHORT", final_size=1.0, confidence=0.7,
        status="open", entry_price=100.0, quantity=1.0, opened_at=now,
        # Stop mesafesi kasıtlı olarak %2 (< %4.5 scalp eşiği) — pump_fade
        # etiketinin scalp sezgiselliğinden ÖNCE geldiğini kanıtlamak için.
        stop_loss_price=102.0, take_profit_price=95.0,
        experiment_bucket="pump_fade_v1",
    )
    with SessionFactory.get_session() as session:
        DecisionPersistor(session).persist(event)
    return event


def test_open_pump_fade_position_is_labeled_in_positions_api(client):
    symbol = f"PFOPEN{uuid4().hex[:8]}"
    _open_pump_fade_position(symbol)

    response = client.get("/api/v1/positions", headers=make_authed_headers(Role.VIEWER))
    assert response.status_code == 200
    positions = {p["symbol"]: p for p in response.json()["positions"]}

    assert positions[symbol]["trade_type"] == "pump_fade"


def test_closed_pump_fade_trade_is_excluded_from_trades_api(client):
    """2026-08-29 — "pump-fade dashboard contamination" düzeltmesi (bkz.
    api/rest/positions.py::list_closed_trades — exclude_experiment_bucket=
    "pump_fade_v1" artık HER ZAMAN uygulanıyor) sonrası bu testin ESKİ
    beklentisi (pump_fade kapalı işleminin GET /trades'te GÖRÜNMESİ)
    kasıtlı olarak TERSİNE döndü — pump_fade artık ana AI performans
    istatistiklerini kirletmesin diye bilinçli olarak hariç tutuluyor.
    GET /positions (açık pozisyonlar) etkilenmedi, bkz. yukarıdaki test."""
    symbol = f"PFCLOSED{uuid4().hex[:8]}"
    event = _open_pump_fade_position(symbol)
    with SessionFactory.get_session() as session:
        DecisionPersistor(session).close_position(
            decision_id=str(event.id), exit_price=95.0, pnl=5.0, closed_at=datetime.now(UTC)
        )

    response = client.get("/api/v1/trades", headers=make_authed_headers(Role.VIEWER))
    assert response.status_code == 200
    trades = {t["symbol"]: t for t in response.json()["trades"]}

    assert symbol not in trades


def test_closed_pump_fade_trade_is_visible_with_explicit_experiment_bucket_param(client):
    """Faz 406-devam — kullanıcı bulgusu (2026-09-03): "kapanmış işlemlerde
    pump-fade işlemlerini göremiyorum." Yukarıdaki koşulsuz dışlama
    Transactions.tsx'teki "Pump-Fade" filtresini de sessizce ölü
    bırakmıştı (her zaman sıfır sonuç). `experiment_bucket=pump_fade_v1`
    query param'ı verilirse dışlamanın YERİNE geçip SADECE bu bucket'ı
    döndürmeli — varsayılan (yukarıdaki) davranış DEĞİŞMEDİ."""
    symbol = f"PFVISIBLE{uuid4().hex[:8]}"
    event = _open_pump_fade_position(symbol)
    with SessionFactory.get_session() as session:
        DecisionPersistor(session).close_position(
            decision_id=str(event.id), exit_price=95.0, pnl=5.0, closed_at=datetime.now(UTC)
        )

    response = client.get(
        "/api/v1/trades", params={"experiment_bucket": "pump_fade_v1"},
        headers=make_authed_headers(Role.VIEWER),
    )
    assert response.status_code == 200
    trades = {t["symbol"]: t for t in response.json()["trades"]}

    assert symbol in trades
    assert trades[symbol]["trade_type"] == "pump_fade"


def test_normal_ai_position_is_not_labeled_pump_fade(client):
    """experiment_bucket boşsa eski sezgisel sınıflandırma (scalp/swing)
    bozulmamalı — bu bir regresyon testi."""
    symbol = f"AIPOS{uuid4().hex[:8]}"
    now = datetime.now(UTC)
    event = DecisionEvent(
        id=uuid4(), timestamp=now, symbol=symbol,
        proposed_direction="LONG", final_action="LONG", final_size=1.0, confidence=0.7,
        status="open", entry_price=100.0, quantity=1.0, opened_at=now,
        stop_loss_price=98.0, take_profit_price=105.0,
    )
    with SessionFactory.get_session() as session:
        DecisionPersistor(session).persist(event)

    response = client.get("/api/v1/positions", headers=make_authed_headers(Role.VIEWER))
    assert response.status_code == 200
    positions = {p["symbol"]: p for p in response.json()["positions"]}

    assert positions[symbol]["trade_type"] == "scalp"
