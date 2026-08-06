"""Faz 215: kullanıcı isteği — "dün ne kadar ROI yapmış, haftalık/aylık/
yıllık ne olmuş" dashboard'da hiç görünmüyordu. /api/v1/performance
gerçek kapanmış işlemlerden (decisions tablosu) günlük/haftalık/aylık/
yıllık PnL + ROI + win rate hesaplıyor."""
from datetime import UTC, datetime
from unittest.mock import patch
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


def _closed_trade(pnl: float, symbol: str):
    now = datetime.now(UTC)
    event = DecisionEvent(
        id=uuid4(), symbol=symbol, proposed_direction="LONG", final_action="LONG",
        final_size=1.0, confidence=0.6,
        status="open", entry_price=100.0, quantity=1.0, opened_at=now,
    )
    with SessionFactory.get_session() as session:
        repo = DecisionPersistor(session)
        repo.persist(event)
        repo.close_position(decision_id=str(event.id), exit_price=100.0, pnl=pnl, closed_at=now)
    return event.id


def test_performance_endpoint_reflects_real_closed_trades():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        symbol = f"PERF{uuid4().hex[:8]}"
        _closed_trade(pnl=50.0, symbol=symbol)
        _closed_trade(pnl=-20.0, symbol=symbol)

        client = _client()
        response = client.get("/api/v1/performance", headers=make_authed_headers(Role.VIEWER))
        assert response.status_code == 200
        body = response.json()

        assert body["all_time"]["trade_count"] >= 2
        assert "daily" in body and "weekly" in body and "monthly" in body and "yearly" in body
        assert body["daily"][0]["trade_count"] >= 2
        assert 0.0 <= body["daily"][0]["win_rate"] <= 1.0
        assert body["starting_capital"] > 0


def test_trades_endpoint_summary_matches_performance_all_time_even_when_table_is_capped():
    """Faz 224: kritik bulgu — kullanıcı: "sürekli işlem alıyor kapatıyor
    ama kapanmış işlem sayısı 100 görünüyor, bir ara 400 küsürdü, bu
    dashboarda güvenemiyorum." Kök neden: GET /trades'in summary'si
    list_closed_trades(limit=...)'ın DÖNDÜRDÜĞÜ (varsayılan 100) dilimden
    hesaplanıyordu, GET /performance ise ayrı (limit=10000) bir hesap
    yapıyordu — aynı isimli iki sayı iki farklı gerçek kümeden geliyordu.
    Bu test, /trades'e KÜÇÜK bir tablo limiti verilse bile (ör. limit=1,
    tabloda tek satır dönse bile) summary.count'un GERÇEK toplamı
    yansıttığını, ve bunun /performance.all_time ile birebir aynı
    olduğunu doğruluyor."""
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        symbol = f"TRADESYNC{uuid4().hex[:8]}"
        _closed_trade(pnl=50.0, symbol=symbol)
        _closed_trade(pnl=-20.0, symbol=symbol)
        _closed_trade(pnl=30.0, symbol=symbol)

        client = _client()
        trades_resp = client.get(
            "/api/v1/trades", params={"limit": 1}, headers=make_authed_headers(Role.VIEWER)
        )
        perf_resp = client.get("/api/v1/performance", headers=make_authed_headers(Role.VIEWER))

        assert trades_resp.status_code == 200 and perf_resp.status_code == 200
        trades_body = trades_resp.json()
        perf_body = perf_resp.json()

        # Tablo satırı gerçekten limitli (1) ama summary limitten bağımsız.
        assert len(trades_body["trades"]) == 1
        assert trades_body["summary"]["count"] == perf_body["all_time"]["trade_count"]
        assert trades_body["summary"]["total_pnl"] == perf_body["all_time"]["total_pnl"]
        assert trades_body["summary"]["win_rate"] == perf_body["all_time"]["win_rate"]
        assert trades_body["summary"]["count"] >= 3
