"""Faz 360 — Gerçek-Zamanlı Pozisyon İzleyici (WebSocket).

Kullanıcı isteği (2026-08-24): "kaymayı azaltalım, açık pozisyonları
kapatmak için sistem fiyat taramalarını anlık yapsın... pozisyon
alırken değil, kapatırken önemli." Kontrol edildi: `close_due_positions_
task` 60sn'de bir, TÜM açık pozisyon sembolleri için (149 benzersiz) REST
isteğiyle çalışıyor — Binance'in paylaşılan hız limiti (15 istek/sn, TÜM
süreçler arası) altında bunu birkaç saniyeye çekmek bile TEK BAŞINA
bütçenin çoğunu tüketirdi (ve önceki bir oturumda tam bu tür bir
çakışma yüzünden gerçek bir kesinti yaşanmıştı). Gerçek "anlık" için
REST polling YETERSİZ.

Bu modül `exchange_gateway/binance/live_feed.py::LiveMarketFeed`'in
(Faz 247-249'dan beri hiç kullanılmayan bir iskelet) aynı WebSocket
deseniyle, ama pozisyon kapatma için: açık pozisyonların sembollerine
Binance'in GERÇEK, ücretsiz trade stream'ine abone olup her tick'te
stop/hedef/likidasyon seviyelerini kontrol ediyor — check aralığı artık
60sn değil, gerçek piyasa tick hızı.

MİMARİ — BİLİNÇLİ TASARIM KARARLARI:
1. **`close_due_positions_task` (REST, 60sn) KALDIRILMADI, GÜVENLİK AĞI
   olarak paralel çalışmaya devam ediyor.** WebSocket bağlantısı
   kopabilir/gecikebilir — REST periyodik tarama bunun ARKASINDAKİ,
   asla tamamen güvenilmeyen bir yedek. Faz 360'ta bulunan gerçek bir
   yarış koşulu (`DecisionPersistor.close_position`'da `WHERE status=
   'open'` şartı YOKTU) düzeltildi — iki yol artık AYNI pozisyonu
   eşzamanlı görse bile SADECE biri gerçekten kapatır, diğeri sessizce
   no-op olur (rowcount=0 -> False).
2. **Kapatma mantığı KOPYALANMADI.** `PositionCloser._process_position_
   at_price()` (services/position_closer.py, close_due_positions'ın
   çıkardığı AYNI metod) burada da çağrılıyor — iki yolun davranışı
   ASLA birbirinden sapmasın diye (breakeven/trailing/fee/funding/
   exit_reason etiketleme mantığı tek bir yerde).
3. **Açık pozisyonlar bellek-içi bir önbellekte tutulur, HER tick'te DB'ye
   gidilmez.** ~SYMBOL_REFRESH_INTERVAL_SECONDS'te bir (15sn) taze
   `list_open_positions()` çekilip {symbol: [pozisyonlar]} olarak
   önbelleğe alınır — sadece GERÇEKTEN bir stop/hedef/likidasyon
   seviyesine değen tick'ler DB'ye gider (taze satırı tekrar okuyup
   kapatmak için).
4. **Sembol seti değişince (yeni pozisyon/tam kapanış) yeniden bağlanılır.**
   Binance'in dinamik subscribe/unsubscribe protokolünü (request/response
   id eşleştirme) KASITLI OLARAK kullanmıyoruz — basit reconnect, ~15sn'de
   bir sembol seti değişikliğini kontrol eder, değiştiyse mevcut bağlantı
   kapatılıp YENİ sembol listesiyle yeniden açılır. Daha basit, daha az
   durum yönetimi, sembol değişikliği bu kadar sık olmadığı için (trading
   cycle ~120sn) kabul edilebilir bir maliyet.
5. **Ayrı, kalıcı bir süreç olarak çalışır** (uvicorn/celery/beat gibi) —
   Celery'nin prefork worker modeline UYMUYOR (kalıcı bir asyncio event
   loop'u gerektiriyor). `python -m services.realtime_position_monitor`
   ile başlatılır.
6. **Gerçek bulgu (ilk canlı deneme, 2026-08-24):** açık pozisyon
   sembolleri arasında Binance'te hiç var olmayan semboller de var —
   hisse senetleri (`AAPL`, RoutingProvider bunları Yahoo'ya yönlendiriyor,
   bkz. `looks_like_binance_pair`) VE `USDT` sonekiyle bitip de gerçekte
   Binance'te listeli olmayan/delist edilmiş token'lar. Binance'in
   combined-stream endpoint'i istenen stream'lerden TEK biri geçersizse
   TÜM bağlantıyı `HTTP 400` ile reddediyor — bu yüzden abone olunacak
   sembol seti, `BinanceAdapter.get_symbols()`'tan (gerçek `exchangeInfo`,
   paylaşılan REST hız limitine tabi, ~30dk'da bir tazelenir) dönen
   GERÇEK listeye göre filtreleniyor. Filtrelenip dışarıda kalan
   pozisyonlar (hisse + Binance'te olmayan token) bu modülün abone
   OLMADIĞI semboller — onlar için tek güvence hâlâ REST güvenlik ağı
   (`close_due_positions_task`, RoutingProvider ile doğru kaynağa zaten
   yönleniyor).
"""
import asyncio
import json
from datetime import UTC, datetime

import structlog
import websockets

from market_data.ingestion.data_provider import looks_like_binance_pair

logger = structlog.get_logger()

SYMBOL_REFRESH_INTERVAL_SECONDS = 15
VALID_SYMBOLS_REFRESH_INTERVAL_SECONDS = 1800
RECONNECT_BACKOFF_SECONDS = 3
NO_SYMBOLS_SLEEP_SECONDS = 5
BINANCE_MAX_STREAMS_PER_CONNECTION = 1024


def _is_price_triggered(pos: dict, price: float) -> bool:
    """Ucuz, bellek-içi bir ön-kontrol — DB'ye SADECE gerçekten bir
    seviyeye değen tick'ler için gidilir. Kesin/nihai karar (breakeven
    ratchet dahil, tam gerçek mantık) PositionCloser._process_position_
    at_price()'ta veriliyor — bu sadece "DB'ye gitmeye değer mi" sorusu."""
    direction = (pos.get("direction") or "").upper()
    stop = pos.get("stop_loss_price")
    target = pos.get("take_profit_price")
    liquidation = pos.get("liquidation_price")
    if direction == "LONG":
        return (
            (stop is not None and price <= stop)
            or (target is not None and price >= target)
            or (liquidation is not None and price <= liquidation)
        )
    if direction == "SHORT":
        return (
            (stop is not None and price >= stop)
            or (target is not None and price <= target)
            or (liquidation is not None and price >= liquidation)
        )
    return False


class RealtimePositionMonitor:
    def __init__(self):
        from market_data.ingestion.data_provider import RoutingProvider
        from services.position_closer import PositionCloser

        self.closer = PositionCloser(RoutingProvider())
        self._positions_by_symbol: dict[str, list[dict]] = {}
        self._valid_binance_symbols: frozenset[str] = frozenset()

    def _fetch_open_positions_by_symbol(self) -> dict[str, list[dict]]:
        from database.repositories.decision_persistor import DecisionPersistor
        from database.session_factory import SessionFactory

        with SessionFactory.get_session() as session:
            positions = DecisionPersistor(session).list_open_positions(limit=None)

        by_symbol: dict[str, list[dict]] = {}
        for pos in positions:
            if pos.get("opened_at") is None or pos.get("entry_price") is None:
                continue
            by_symbol.setdefault(pos["symbol"], []).append(pos)
        return by_symbol

    async def _refresh_loop(self) -> None:
        while True:
            try:
                self._positions_by_symbol = await asyncio.to_thread(self._fetch_open_positions_by_symbol)
            except Exception as exc:
                logger.warning("realtime_position_monitor_refresh_failed", error=str(exc))
            await asyncio.sleep(SYMBOL_REFRESH_INTERVAL_SECONDS)

    @staticmethod
    async def _fetch_valid_binance_symbols() -> frozenset[str]:
        from exchange_gateway.binance.adapter import BinanceAdapter

        adapter = BinanceAdapter()
        await adapter.connect()
        try:
            symbols = await adapter.get_symbols()
        finally:
            await adapter.disconnect()
        return frozenset(s.symbol for s in symbols)

    async def _refresh_valid_symbols_loop(self) -> None:
        while True:
            try:
                self._valid_binance_symbols = await self._fetch_valid_binance_symbols()
                logger.info(
                    "realtime_position_monitor_valid_symbols_refreshed",
                    count=len(self._valid_binance_symbols),
                )
            except Exception as exc:
                logger.warning("realtime_position_monitor_valid_symbols_refresh_failed", error=str(exc))
            await asyncio.sleep(VALID_SYMBOLS_REFRESH_INTERVAL_SECONDS)

    def _subscribable_symbols(self) -> frozenset[str]:
        return frozenset(
            s for s in self._positions_by_symbol
            if looks_like_binance_pair(s) and s in self._valid_binance_symbols
        )

    def _close_triggered_positions_sync(self, symbol: str, price: float) -> None:
        from database.repositories.decision_persistor import DecisionPersistor
        from database.session_factory import SessionFactory

        candidates = [p for p in self._positions_by_symbol.get(symbol, []) if _is_price_triggered(p, price)]
        if not candidates:
            return

        now = datetime.now(UTC)
        with SessionFactory.get_session() as session:
            repo = DecisionPersistor(session)
            for pos in candidates:
                # Faz 360 — bellek-içi önbellek en fazla SYMBOL_REFRESH_
                # INTERVAL_SECONDS kadar bayat olabilir (bir önceki tick
                # tarafından ZATEN kapatılmış olabilir, ya da REST güvenlik
                # ağı kapatmış olabilir) — TAZE satırı tekrar okuyup HÂLÂ
                # açık mı diye kontrol ediyoruz. close_position()'daki
                # WHERE status='open' şartı zaten son bir güvenlik ağı,
                # ama gereksiz bir _process_position_at_price çağrısını
                # (fee/funding/MAE-MFE hesabı dahil) burada erken atlamak
                # daha verimli.
                fresh = repo.get_by_id(str(pos["id"]))
                if fresh is None or fresh.get("status") != "open":
                    continue
                try:
                    result = self.closer._process_position_at_price(fresh, price, repo, now)
                except Exception as exc:
                    logger.warning(
                        "realtime_position_monitor_close_failed",
                        symbol=symbol, decision_id=str(pos["id"]), error=str(exc),
                    )
                    continue
                if result is not None:
                    logger.info(
                        "realtime_position_monitor_closed_position",
                        symbol=symbol, decision_id=str(pos["id"]),
                        exit_reason=result["closed_entry"]["exit_reason"],
                        pnl=result["closed_entry"]["pnl"],
                    )

    async def _handle_tick(self, symbol: str, price: float) -> None:
        if symbol not in self._positions_by_symbol:
            return
        await asyncio.to_thread(self._close_triggered_positions_sync, symbol, price)

    @staticmethod
    def _stream_url(symbols: list[str]) -> str:
        streams = "/".join(f"{s.lower()}@trade" for s in symbols)
        return f"wss://stream.binance.com:9443/stream?streams={streams}"

    async def _run_stream_until_symbols_change(self, symbols: frozenset[str]) -> None:
        url = self._stream_url(sorted(symbols)[:BINANCE_MAX_STREAMS_PER_CONNECTION])
        logger.info("realtime_position_monitor_connecting", symbol_count=len(symbols))
        async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
            logger.info("realtime_position_monitor_connected", symbol_count=len(symbols))
            async for msg in ws:
                raw = json.loads(msg)
                data = raw["data"] if "data" in raw and "stream" in raw else raw
                sym = data.get("s")
                price_raw = data.get("p")
                if sym and price_raw is not None:
                    try:
                        await self._handle_tick(sym.upper(), float(price_raw))
                    except Exception as exc:
                        logger.warning("realtime_position_monitor_tick_handling_failed", error=str(exc))
                if self._subscribable_symbols() != symbols:
                    # Sembol seti değişti (yeni pozisyon açıldı, bir
                    # sembolün TÜM pozisyonları kapandı, ya da geçerli
                    # Binance sembol listesi tazelendi) — yeniden bağlan.
                    return

    async def run(self) -> None:
        self._positions_by_symbol = await asyncio.to_thread(self._fetch_open_positions_by_symbol)
        self._valid_binance_symbols = await self._fetch_valid_binance_symbols()
        refresh_task = asyncio.create_task(self._refresh_loop())
        valid_symbols_task = asyncio.create_task(self._refresh_valid_symbols_loop())
        try:
            while True:
                symbols = self._subscribable_symbols()
                if not symbols:
                    await asyncio.sleep(NO_SYMBOLS_SLEEP_SECONDS)
                    continue
                try:
                    await self._run_stream_until_symbols_change(symbols)
                except (websockets.ConnectionClosed, OSError) as exc:
                    logger.warning("realtime_position_monitor_ws_disconnected", error=str(exc))
                    await asyncio.sleep(RECONNECT_BACKOFF_SECONDS)
                except Exception as exc:
                    logger.warning("realtime_position_monitor_ws_error", error=str(exc))
                    await asyncio.sleep(RECONNECT_BACKOFF_SECONDS)
        finally:
            refresh_task.cancel()
            valid_symbols_task.cancel()


async def _main() -> None:
    logger.info("realtime_position_monitor_starting")
    monitor = RealtimePositionMonitor()
    await monitor.run()


if __name__ == "__main__":
    asyncio.run(_main())
