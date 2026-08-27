"""Faz 365 — Backlog #49 ("MempoolAgent", isim kullanıcı onayıyla
Liquidation'a çevrildi — gerçek veri kaynağı mempool değil, Binance
Futures'ın zorunlu-kapanış akışı). Kullanıcı kararı (2026-08-26):
"veri toplayıp ölçebiliyorsak iyi, en önemli kısım orası" — bu modül
SADECE veriyi gerçek zamanlı toplayıp `liquidation_events`'e yazar,
hiçbir yön/skor kararı vermiyor (ajan/oylama katmanı ayrı, henüz
yazılmadı).

`services/realtime_position_monitor.py` ile AYNI mimari desen: ayrı,
kalıcı bir asyncio süreci (Celery prefork worker modeline uymuyor),
basit reconnect/backoff. Binance'in `!forceOrder@arr` (TÜM USDT-M
Futures sembolleri, tek bağlantı, kimliksiz/ücretsiz) akışına abone —
`realtime_position_monitor`'ın aksine sembol seti yönetimi YOK, akış
zaten global."""
import asyncio
import json
from datetime import UTC, datetime

import structlog
import websockets

logger = structlog.get_logger()

STREAM_URL = "wss://fstream.binance.com/ws/!forceOrder@arr"
RECONNECT_BACKOFF_SECONDS = 3


def _parse_force_order(raw: dict) -> dict | None:
    order = raw.get("o")
    if not order:
        return None
    symbol = order.get("s")
    side = order.get("S")
    quantity = order.get("q")
    price = order.get("ap") or order.get("p")
    trade_time_ms = order.get("T")
    if not symbol or side not in ("SELL", "BUY") or quantity is None or price is None or trade_time_ms is None:
        return None

    quantity_f = float(quantity)
    price_f = float(price)
    # Binance'in SELL/BUY'ı zorunlu emrin YÖNÜ — SELL = LONG pozisyon
    # likide edildi (zorunlu satış), BUY = SHORT pozisyon likide edildi
    # (zorunlu alış). Okunurluk için likide olan pozisyonun yönüne
    # çevriliyor, ham veriden kayıpsız türetilebilir.
    liquidated_side = "LONG" if side == "SELL" else "SHORT"

    return {
        "symbol": symbol.upper(),
        "time": datetime.fromtimestamp(int(trade_time_ms) / 1000, tz=UTC),
        "liquidated_side": liquidated_side,
        "price": price_f,
        "quantity": quantity_f,
        "notional_usd": round(price_f * quantity_f, 4),
    }


def _persist_event(event: dict) -> None:
    from sqlalchemy import text

    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        session.execute(
            text(
                """
                INSERT INTO liquidation_events (symbol, time, liquidated_side, price, quantity, notional_usd)
                VALUES (:symbol, :time, :liquidated_side, :price, :quantity, :notional_usd)
                """
            ),
            event,
        )
        session.commit()


class BinanceLiquidationListener:
    async def _handle_message(self, raw_msg: str) -> None:
        try:
            raw = json.loads(raw_msg)
            event = _parse_force_order(raw)
        except Exception as exc:
            logger.warning("liquidation_listener_parse_failed", error=str(exc))
            return
        if event is None:
            return
        try:
            await asyncio.to_thread(_persist_event, event)
        except Exception as exc:
            logger.warning("liquidation_listener_persist_failed", error=str(exc), symbol=event.get("symbol"))

    async def run(self) -> None:
        while True:
            try:
                logger.info("liquidation_listener_connecting")
                async with websockets.connect(STREAM_URL, ping_interval=20, ping_timeout=20) as ws:
                    logger.info("liquidation_listener_connected")
                    async for msg in ws:
                        await self._handle_message(msg)
            except (websockets.ConnectionClosed, OSError) as exc:
                logger.warning("liquidation_listener_ws_disconnected", error=str(exc))
                await asyncio.sleep(RECONNECT_BACKOFF_SECONDS)
            except Exception as exc:
                logger.warning("liquidation_listener_ws_error", error=str(exc))
                await asyncio.sleep(RECONNECT_BACKOFF_SECONDS)


async def _main() -> None:
    logger.info("liquidation_listener_starting")
    await BinanceLiquidationListener().run()


if __name__ == "__main__":
    asyncio.run(_main())
