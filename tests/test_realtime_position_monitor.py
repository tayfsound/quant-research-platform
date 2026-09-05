"""Faz 414 (2026-09-06) — kullanıcı bulgusu: gerçek-zamanlı WS izleyici
"keepalive ping timeout" ile sık sık kopuyordu (log: ortalama her 10-30
dakikada bir), REST güvenlik ağı bazı pencerelerde bunu yeterince hızlı
telafi edemeyip pozisyonların planlanan stop mesafesinin 6,5 katına kadar
aşarak kapanmasına yol açtı. Kök neden: _handle_tick, o sembolde HERHANGİ
bir açık pozisyon varsa HER trade tick'inde asyncio.to_thread ile tam bir
thread-havuzu gidiş-dönüşü ödüyordu — ucuz/saf _is_price_triggered kontrolü
artık thread'e gitmeden ÖNCE senkron çalıştırılıyor."""
import asyncio

import pytest

from services.realtime_position_monitor import RealtimePositionMonitor


@pytest.fixture
def monitor():
    return RealtimePositionMonitor()


async def _run(monitor, symbol, price):
    await monitor._handle_tick(symbol, price)


def test_tick_far_from_any_trigger_never_dispatches_to_a_thread(monkeypatch, monitor):
    monitor._positions_by_symbol = {
        "BTCUSDT": [{"id": "1", "direction": "LONG", "stop_loss_price": 50000.0, "take_profit_price": 70000.0}],
    }
    called = []

    async def fake_to_thread(func, *args):
        called.append((func, args))

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

    asyncio.run(_run(monitor, "BTCUSDT", 60000.0))

    assert called == []


def test_tick_at_stop_level_dispatches_to_a_thread(monkeypatch, monitor):
    monitor._positions_by_symbol = {
        "BTCUSDT": [{"id": "1", "direction": "LONG", "stop_loss_price": 50000.0, "take_profit_price": 70000.0}],
    }
    called = []

    async def fake_to_thread(func, *args):
        called.append((func, args))

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

    asyncio.run(_run(monitor, "BTCUSDT", 49000.0))

    assert len(called) == 1
    assert called[0][1] == ("BTCUSDT", 49000.0)


def test_tick_for_symbol_with_no_open_position_never_dispatches(monkeypatch, monitor):
    monitor._positions_by_symbol = {}
    called = []

    async def fake_to_thread(func, *args):
        called.append((func, args))

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

    asyncio.run(_run(monitor, "ETHUSDT", 3000.0))

    assert called == []
