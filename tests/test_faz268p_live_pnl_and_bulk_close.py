"""Faz 268p — kullanıcı isteği: "her açık pozisyonun anlık kâr/zararını
göster (sembol adının civarında), kârdakileri toplu kapat ama komisyona
ezilmeyecek şekilde." Bu testler GET /positions'ın her açık pozisyona
current_price/net_unrealized_pnl eklediğini ve POST /positions/close-
profitable'ın SADECE komisyon sonrası net kârlı pozisyonları kapattığını
(zarardaki/nötr pozisyonlara asla dokunmadığını) doğruluyor. Gerçek ağ
çağrısı yerine RoutingProvider.get_ohlcv monkeypatch'lenip deterministik
bir fiyat veriliyor — testin hızı/kararlılığı gerçek Binance gecikmesine
bağlı kalmasın diye (PositionCloser testlerinin zaten kullandığı
_FixedPriceProvider deseninin API-seviyesi eşdeğeri)."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from contracts.auth import Role
from contracts.decision_event import DecisionEvent
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from tests.auth_helpers import make_authed_headers


def _open_position(symbol: str, direction: str = "LONG", quantity: float = 1.0, entry_price: float = 100.0):
    now = datetime.now(UTC)
    event = DecisionEvent(
        id=uuid4(), timestamp=now, symbol=symbol,
        proposed_direction=direction, final_action=direction, final_size=quantity, confidence=0.7,
        status="open", entry_price=entry_price, quantity=quantity, opened_at=now,
        stop_loss_price=90.0 if direction == "LONG" else 110.0,
        take_profit_price=120.0 if direction == "LONG" else 80.0,
    )
    with SessionFactory.get_session() as session:
        DecisionPersistor(session).persist(event)
    return event


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


def _patch_price(monkeypatch, price: float):
    from market_data.ingestion.ohlcv import OHLCV
    from market_data.ingestion import data_provider as dp_module

    def fake_get_ohlcv(self, symbol, timeframe, limit=1):
        now = datetime.now(UTC)
        return [OHLCV(timestamp=now, open=price, high=price, low=price, close=price, volume=1.0)]

    monkeypatch.setattr(dp_module.RoutingProvider, "get_ohlcv", fake_get_ohlcv)


def test_get_positions_includes_net_unrealized_pnl_for_open_positions(client, monkeypatch):
    symbol = f"LIVEPNL{uuid4().hex[:8]}"
    event = _open_position(symbol, direction="LONG", quantity=1.0, entry_price=100.0)
    _patch_price(monkeypatch, 110.0)

    res = client.get("/api/v1/positions", headers=make_authed_headers(Role.VIEWER))
    assert res.status_code == 200
    body = res.json()
    match = next(p for p in body["positions"] if p["id"] == str(event.id))
    assert match["current_price"] == 110.0
    assert match["net_unrealized_pnl"] is not None
    assert match["net_unrealized_pnl"] > 0  # %10 hareket, komisyonu rahatça karşılar


def test_close_profitable_closes_only_net_positive_positions(client, monkeypatch):
    profitable_symbol = f"BULKPROFIT{uuid4().hex[:8]}"
    losing_symbol = f"BULKLOSS{uuid4().hex[:8]}"
    profitable = _open_position(profitable_symbol, direction="LONG", quantity=1.0, entry_price=100.0)
    losing = _open_position(losing_symbol, direction="LONG", quantity=1.0, entry_price=100.0)

    # Aynı RoutingProvider tüm sembollere aynı fiyatı döndürüyor (basit test
    # provider'ı) — ama pozisyonların yönü/giriş fiyatı farklı olduğu için
    # biri kârlı, diğeri zararlı olacak şekilde AYRI fiyat lazım. Sembole
    # göre farklı fiyat dönen bir provider kullanıyoruz.
    from market_data.ingestion.ohlcv import OHLCV
    from market_data.ingestion import data_provider as dp_module

    def fake_get_ohlcv(self, symbol, timeframe, limit=1):
        now = datetime.now(UTC)
        price = 130.0 if symbol == profitable_symbol else 95.0  # biri kârlı, biri zararlı
        return [OHLCV(timestamp=now, open=price, high=price, low=price, close=price, volume=1.0)]

    monkeypatch.setattr(dp_module.RoutingProvider, "get_ohlcv", fake_get_ohlcv)

    res = client.post("/api/v1/positions/close-profitable", headers=make_authed_headers(Role.OPERATOR))
    assert res.status_code == 200
    body = res.json()
    closed_ids = {c["decision_id"] for c in body["closed"]}
    assert str(profitable.id) in closed_ids
    assert str(losing.id) not in closed_ids

    with SessionFactory.get_session() as session:
        persistor = DecisionPersistor(session)
        profitable_row = persistor.get_by_id(str(profitable.id))
        losing_row = persistor.get_by_id(str(losing.id))
    assert profitable_row["status"] == "closed"
    assert losing_row["status"] == "open"  # zarardaki pozisyona DOKUNULMADI


def test_close_profitable_does_not_close_a_gain_too_small_to_cover_commission(client, monkeypatch):
    """Kullanıcının tam olarak istediği: "komisyona ezilmeyecek şekilde."""
    symbol = f"TINYGAIN{uuid4().hex[:8]}"
    tiny_gain = _open_position(symbol, direction="LONG", quantity=1.0, entry_price=100.0)
    _patch_price(monkeypatch, 100.01)  # ihmal edilebilir hareket, komisyonun çok altında

    res = client.post("/api/v1/positions/close-profitable", headers=make_authed_headers(Role.OPERATOR))
    assert res.status_code == 200
    closed_ids = {c["decision_id"] for c in res.json()["closed"]}
    assert str(tiny_gain.id) not in closed_ids

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(tiny_gain.id))
    assert row["status"] == "open"
