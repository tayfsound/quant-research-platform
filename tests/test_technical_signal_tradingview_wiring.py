"""Faz 193: TradingView webhook alarmı artık gerçekten TechnicalAgent'a
ikinci görüş olarak akıyor — ExternalSignalRepository zaten vardı
(api/rest/webhooks.py yazıyordu) ama hiçbir agent onu hiç okumuyordu."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import text

from contracts.context import CognitiveCycleContext
from database.session_factory import SessionFactory
from services.context_adapter import ContextAdapter


def _save_signal(symbol: str, signal: str, age_seconds: float = 0.0):
    with SessionFactory.get_session() as session:
        session.execute(
            text(
                "INSERT INTO external_signals (id, time, source, symbol, signal, payload) "
                "VALUES (:id, :time, 'tradingview', :symbol, :signal, '{}'::jsonb)"
            ),
            {
                "id": str(uuid4()),
                "time": datetime.now(UTC) - timedelta(seconds=age_seconds),
                "symbol": symbol,
                "signal": signal,
            },
        )
        session.commit()


def test_to_technical_normalizes_a_fresh_buy_alert_to_bullish():
    symbol = f"TVSIG{uuid4().hex[:8]}"
    _save_signal(symbol, "strong buy")

    ctx = CognitiveCycleContext(market={"symbol": symbol})
    result = ContextAdapter().to_technical(ctx)

    assert result.external_signal == "bullish"
    assert result.external_signal_source == "tradingview"


def test_to_technical_normalizes_a_fresh_sell_alert_to_bearish():
    symbol = f"TVSIG{uuid4().hex[:8]}"
    _save_signal(symbol, "SHORT entry")

    ctx = CognitiveCycleContext(market={"symbol": symbol})
    result = ContextAdapter().to_technical(ctx)

    assert result.external_signal == "bearish"


def test_to_technical_ignores_a_stale_alert():
    symbol = f"TVSIG{uuid4().hex[:8]}"
    _save_signal(symbol, "buy", age_seconds=3600)  # 1 saat önce, 30dk eşiğinin üstünde

    ctx = CognitiveCycleContext(market={"symbol": symbol})
    result = ContextAdapter().to_technical(ctx)

    assert result.external_signal is None


def test_to_technical_ignores_unrecognized_alert_text():
    symbol = f"TVSIG{uuid4().hex[:8]}"
    _save_signal(symbol, "ping test")  # tanınan bir anahtar kelime yok

    ctx = CognitiveCycleContext(market={"symbol": symbol})
    result = ContextAdapter().to_technical(ctx)

    assert result.external_signal is None


def test_to_technical_no_signal_at_all_for_unknown_symbol():
    ctx = CognitiveCycleContext(market={"symbol": f"NEVERALERTED{uuid4().hex[:8]}"})
    result = ContextAdapter().to_technical(ctx)

    assert result.external_signal is None
