"""exchange_gateway/binance/live_feed.py — gerçek bulgu: bu sınıf hiçbir
yerden çağrılmıyordu ve MarketSnapshotEvent'i zorunlu `exchange` alanı
olmadan construct ediyordu (hiç çalıştırılmamış olsaydı ValidationError
verirdi). Ayrıca sadece event bus'a publish ediyordu — market_trades'e
hiçbir zaman gerçek bir trade yazılmıyordu."""
import asyncio
from uuid import uuid4

import pytest

from contracts.market_data import DataSource
from database.repositories.market_data_repository import MarketDataRepository
from database.session_factory import SessionFactory
from exchange_gateway.binance.live_feed import LiveMarketFeed


@pytest.mark.asyncio
async def test_handle_trade_message_persists_real_trade_with_correct_side():
    symbol = f"LIVEFEED{uuid4().hex[:6]}".upper()
    feed = LiveMarketFeed(symbols=[symbol.lower()])

    # Gerçek bir Binance @trade mesajının şekli.
    await feed.handle_trade_message({
        "s": symbol, "p": "64123.45", "q": "0.015", "T": 1785931200000, "m": False,
    })

    with SessionFactory.get_session() as session:
        trades = MarketDataRepository(session).get_recent_trades(symbol, limit=1)

    assert len(trades) == 1
    assert trades[0]["price"] == 64123.45
    assert trades[0]["quantity"] == 0.015
    assert trades[0]["side"] == "buy"  # m=False -> alıcı taker


@pytest.mark.asyncio
async def test_handle_trade_message_derives_sell_side_from_maker_flag():
    symbol = f"LIVEFEEDSELL{uuid4().hex[:6]}".upper()
    feed = LiveMarketFeed(symbols=[symbol.lower()])

    await feed.handle_trade_message({
        "s": symbol, "p": "100.0", "q": "1.0", "T": 1785931200000, "m": True,
    })

    with SessionFactory.get_session() as session:
        trades = MarketDataRepository(session).get_recent_trades(symbol, limit=1)

    assert trades[0]["side"] == "sell"  # m=True -> satıcı taker


def test_single_symbol_stream_url():
    feed = LiveMarketFeed(symbols=["btcusdt"])
    assert feed._stream_url() == "wss://stream.binance.com:9443/ws/btcusdt@trade"


def test_multi_symbol_stream_url_uses_combined_endpoint():
    feed = LiveMarketFeed(symbols=["btcusdt", "ethusdt"])
    url = feed._stream_url()
    assert "stream?streams=" in url
    assert "btcusdt@trade" in url
    assert "ethusdt@trade" in url


@pytest.mark.asyncio
async def test_real_binance_websocket_delivers_and_persists_one_real_trade():
    """Gerçek Binance WS'e bağlanıp GERÇEK bir trade mesajı alıp DB'ye
    yazdığını doğrular — max_messages=1 ile sonsuz döngüye girmeden,
    asyncio.wait_for ile sınırlı bir zaman aşımıyla."""
    symbol = "btcusdt"
    with SessionFactory.get_session() as session:
        before = len(MarketDataRepository(session).get_recent_trades("BTCUSDT", limit=100000))

    feed = LiveMarketFeed(symbols=[symbol])
    await asyncio.wait_for(feed.start(max_messages=1), timeout=20)

    with SessionFactory.get_session() as session:
        after = len(MarketDataRepository(session).get_recent_trades("BTCUSDT", limit=100000))

    assert after == before + 1
