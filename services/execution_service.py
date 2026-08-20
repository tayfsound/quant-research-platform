"""Faz 315 — Execution Layer, Faz 1: gerçek Binance Futures Testnet emir
gönderiminin tek orkestrasyon noktası. contracts/exchange.py::
OrderExecutionPort'un ARKASINDA çalışır — services/decision_recorder.py
(açılış) ve services/position_closer.py (kapanış + breakeven ratchet)
bu servisi çağırır, borsa adaptörüne DOĞRUDAN hiçbiri dokunmaz.

Tasarım ilkesi (plandan): bir leveraged pozisyonun borsada KORUMASIZ
(çıplak — ne stop ne hedef emri) kalmasına ASLA izin verilmez. Stop
güncellemesi (breakeven ratchet) başarısız olursa önce eski fiyatta
yeniden koymayı dener, o da başarısız olursa pozisyonu güvenlik amaçlı
acil kapatır — sınırsız süre korumasız bir pozisyon bırakmak, ratchet'in
kendisinden çok daha büyük bir risk."""
import uuid
from dataclasses import dataclass

import structlog

from config import get_settings
from contracts.exchange import OrderExecutionPort, OrderSide, OrderStatus, OrderType, PlaceOrderRequest
from database.repositories.event_log_repository import EventLogRepository

logger = structlog.get_logger()

_ENTRY_FILL_POLL_ATTEMPTS = 10
_ENTRY_FILL_POLL_INTERVAL_SECONDS = 1.0
_FILLED_STATUSES = {"FILLED"}
_TERMINAL_UNFILLED_STATUSES = {"CANCELED", "EXPIRED", "REJECTED"}


def _client_order_id(decision_id: uuid.UUID, role: str) -> str:
    """Deterministik idempotency anahtarı — AYNI decision_id için AYNI
    rol (giriş/stop/hedef) her zaman AYNI client_order_id'yi üretir, bu
    yüzden bir isteğin yanlışlıkla iki kez gönderilmesi (ör. Celery
    retry) borsa tarafında -2011 "Duplicate order" ile GERÇEKTEN
    yakalanabilir. Binance'in newClientOrderId ≤36 karakter sınırına
    (3 harf rol öneki + 32 karakter hex UUID = 35) rahatça sığıyor."""
    return f"qrp{role}{decision_id.hex}"


@dataclass
class OpenPositionResult:
    entry_price: float
    executed_qty: float
    exchange_order_id: str
    exchange_client_order_id: str
    exchange_stop_order_id: str | None
    exchange_tp_order_id: str | None


@dataclass
class StopUpdateResult:
    # new_stop_order_id None SADECE emergency_closed=True iken olur —
    # pozisyon artık yok, çağıran onu "closed" olarak ele almalı.
    new_stop_order_id: str | None
    achieved_stop_price: float | None
    emergency_closed: bool = False


class ExecutionService:
    def __init__(self, adapter: OrderExecutionPort | None = None):
        self._adapter = adapter if adapter is not None else self._build_default_adapter()

    @staticmethod
    def _build_default_adapter() -> OrderExecutionPort | None:
        """Gerçek testnet anahtarları .env'de yoksa (henüz kurulum
        yapılmadıysa) None — is_configured() False döner, çağıranlar
        (DecisionRecorder/PositionCloser) bunu "simulated" moddaymış gibi
        ele almaya devam eder. FRED_API_KEY/HELIUS_API_KEY ile AYNI
        fail-closed desen."""
        settings = get_settings()
        if not settings.BINANCE_FUTURES_TESTNET_API_KEY or not settings.BINANCE_FUTURES_TESTNET_API_SECRET:
            return None
        from exchange_gateway.binance.futures_execution_adapter import BinanceFuturesExecutionAdapter

        return BinanceFuturesExecutionAdapter(
            api_key=settings.BINANCE_FUTURES_TESTNET_API_KEY,
            api_secret=settings.BINANCE_FUTURES_TESTNET_API_SECRET,
            testnet=True,
        )

    def is_configured(self) -> bool:
        return self._adapter is not None

    def _entry_side(self, direction: str) -> OrderSide:
        return OrderSide.BUY if direction.upper() == "LONG" else OrderSide.SELL

    def _protective_side(self, direction: str) -> OrderSide:
        # Koruma emirleri girişin TERSİ yöndedir (LONG'u kapatan SELL,
        # SHORT'u kapatan BUY) — reduce_only ile sadece pozisyonu azaltır.
        return OrderSide.SELL if direction.upper() == "LONG" else OrderSide.BUY

    def _wait_for_fill(self, symbol: str, initial: OrderStatus) -> OrderStatus | None:
        """MARKET emirleri genelde anında dolar (Binance'in senkron REST
        yanıtı çoğu zaman zaten FILLED döner) ama garanti değil — kısa,
        sınırlı bir zaman aşımıyla (~10sn) gerçek durumu sorgular.
        Belirsiz kalırsa (hâlâ dolmamış) None — asla tahmini bir dolum
        uydurulmaz."""
        import time

        status = initial
        if status.status in _FILLED_STATUSES:
            return status
        if status.status in _TERMINAL_UNFILLED_STATUSES:
            return None
        for _ in range(_ENTRY_FILL_POLL_ATTEMPTS):
            time.sleep(_ENTRY_FILL_POLL_INTERVAL_SECONDS)
            status = self._adapter.get_order_status(symbol, initial.exchange_order_id)
            if status is None:
                return None
            if status.status in _FILLED_STATUSES:
                return status
            if status.status in _TERMINAL_UNFILLED_STATUSES:
                return None
        return None

    def open_position(
        self,
        decision_id: uuid.UUID,
        symbol: str,
        direction: str,
        quantity: float,
        stop_loss_price: float,
        take_profit_price: float,
    ) -> OpenPositionResult | None:
        """Gerçek MARKET giriş emri + hemen ardından STOP_MARKET/
        TAKE_PROFIT_MARKET koruma emirleri. Herhangi bir adım belirsiz/
        başarısız kalırsa (giriş dolmadı YA DA koruma emirleri
        yerleşmedi) fail-closed None döner — çağıran (DecisionRecorder)
        "open" YAZMAZ, deneme başarısız olarak kaydedilir. Giriş dolup
        koruma emirleri başarısız olursa, pozisyonu korumasız bırakmak
        yerine ACİL kapatılır (aynı "çıplak pozisyon asla" ilkesi)."""
        if not self.is_configured():
            return None

        entry_req = PlaceOrderRequest(
            symbol=symbol,
            side=self._entry_side(direction),
            order_type=OrderType.MARKET,
            quantity=quantity,
            client_order_id=_client_order_id(decision_id, "e"),
        )
        try:
            initial = self._adapter.place_order(entry_req)
        except Exception as exc:
            logger.warning("execution_open_entry_failed", symbol=symbol, decision_id=str(decision_id), error=str(exc))
            return None

        filled = self._wait_for_fill(symbol, initial)
        if filled is None or filled.avg_price is None or filled.executed_qty <= 0:
            logger.warning(
                "execution_open_entry_not_confirmed_filled", symbol=symbol, decision_id=str(decision_id)
            )
            return None

        protective_side = self._protective_side(direction)
        stop_req = PlaceOrderRequest(
            symbol=symbol,
            side=protective_side,
            order_type=OrderType.STOP_MARKET,
            quantity=filled.executed_qty,
            client_order_id=_client_order_id(decision_id, "s"),
            stop_price=stop_loss_price,
            reduce_only=True,
        )
        tp_req = PlaceOrderRequest(
            symbol=symbol,
            side=protective_side,
            order_type=OrderType.TAKE_PROFIT_MARKET,
            quantity=filled.executed_qty,
            client_order_id=_client_order_id(decision_id, "t"),
            stop_price=take_profit_price,
            reduce_only=True,
        )
        try:
            stop_status = self._adapter.place_order(stop_req)
            tp_status = self._adapter.place_order(tp_req)
        except Exception as exc:
            logger.critical(
                "execution_open_protective_orders_failed_emergency_closing",
                symbol=symbol, decision_id=str(decision_id), error=str(exc),
            )
            self._emergency_close(symbol, direction, filled.executed_qty, decision_id, reason="protective_order_placement_failed")
            return None

        return OpenPositionResult(
            entry_price=filled.avg_price,
            executed_qty=filled.executed_qty,
            exchange_order_id=filled.exchange_order_id,
            exchange_client_order_id=filled.client_order_id,
            exchange_stop_order_id=stop_status.exchange_order_id,
            exchange_tp_order_id=tp_status.exchange_order_id,
        )

    def update_stop_price(
        self,
        decision_id: uuid.UUID,
        symbol: str,
        direction: str,
        quantity: float,
        old_stop_order_id: str,
        old_stop_price: float,
        new_stop_price: float,
    ) -> StopUpdateResult:
        """Breakeven/trailing ratchet — eski STOP_MARKET emrini iptal
        edip yenisini (daha sıkı fiyatta) koyar. Yeni emir başarısız
        olursa ÖNCE eski fiyatta bir stop'u YENİDEN koymayı dener
        (koruma her zaman önce gelir); o da başarısız olursa pozisyon
        güvenlik amaçlı ACİL kapatılır — asla sınırsız süre korumasız
        bırakılmaz."""
        try:
            self._adapter.cancel_order(symbol, old_stop_order_id)
        except Exception as exc:
            logger.warning(
                "execution_stop_update_cancel_failed", symbol=symbol, decision_id=str(decision_id), error=str(exc)
            )
            # İptal başarısız olsa bile devam ediyoruz — eski emir hâlâ
            # yerinde olabilir, bu durumda yeni emri koymak dener denemez
            # borsa muhtemelen -2022/ReduceOnly çakışmasıyla reddedecek,
            # o zaman zaten "eski stop hâlâ korumada" senaryosuna düşeriz.

        protective_side = self._protective_side(direction)
        new_stop_req = PlaceOrderRequest(
            symbol=symbol,
            side=protective_side,
            order_type=OrderType.STOP_MARKET,
            quantity=quantity,
            # Her ratchet denemesi İÇİN benzersiz bir rol damgası
            # gerekiyor (aynı client_order_id'yi iki kez kullanmak
            # -2011'e çarpar) — decision_id + hedef fiyatın kısa bir
            # özeti idempotency'yi korurken benzersizliği sağlıyor.
            client_order_id=_client_order_id(decision_id, f"s{round(new_stop_price, 8)}")[:36],
            stop_price=new_stop_price,
            reduce_only=True,
        )
        try:
            new_status = self._adapter.place_order(new_stop_req)
            return StopUpdateResult(new_stop_order_id=new_status.exchange_order_id, achieved_stop_price=new_stop_price)
        except Exception as exc:
            logger.warning(
                "execution_stop_update_new_order_failed_attempting_reinstate",
                symbol=symbol, decision_id=str(decision_id), error=str(exc),
            )

        # Yeni (sıkı) stop başarısız — pozisyon şu an KORUMASIZ. Eski
        # fiyatta bir stop'u YENİDEN koymayı dene (tek deneme).
        reinstate_req = PlaceOrderRequest(
            symbol=symbol,
            side=protective_side,
            order_type=OrderType.STOP_MARKET,
            quantity=quantity,
            client_order_id=_client_order_id(decision_id, f"r{round(old_stop_price, 8)}")[:36],
            stop_price=old_stop_price,
            reduce_only=True,
        )
        try:
            reinstated = self._adapter.place_order(reinstate_req)
            logger.warning(
                "execution_stop_update_reinstated_old_price",
                symbol=symbol, decision_id=str(decision_id), old_stop_price=old_stop_price,
            )
            return StopUpdateResult(new_stop_order_id=reinstated.exchange_order_id, achieved_stop_price=old_stop_price)
        except Exception as exc:
            logger.critical(
                "execution_stop_update_naked_position_emergency_closing",
                symbol=symbol, decision_id=str(decision_id), error=str(exc),
            )
            self._emergency_close(symbol, direction, quantity, decision_id, reason="stop_reinstate_failed")
            return StopUpdateResult(new_stop_order_id=None, achieved_stop_price=None, emergency_closed=True)

    def _emergency_close(self, symbol: str, direction: str, quantity: float, decision_id: uuid.UUID, reason: str) -> None:
        """Korumasız kalan bir pozisyonu GERÇEK bir MARKET emriyle
        kapatır — sınırsız süre korumasız (ne stop ne hedef emri olan)
        bir leveraged pozisyon bırakmak, tek seferlik bir kapanış
        maliyetinden çok daha büyük bir risk. Bu ÇOK nadir, kritik bir
        yol — her zaman EventLogRepository'ye kalıcı olarak yazılıyor,
        sessizce geçilmiyor."""
        close_req = PlaceOrderRequest(
            symbol=symbol,
            side=self._protective_side(direction),
            order_type=OrderType.MARKET,
            quantity=quantity,
            client_order_id=_client_order_id(decision_id, "x"),
            reduce_only=True,
        )
        try:
            self._adapter.place_order(close_req)
            outcome = "closed"
        except Exception as exc:
            logger.critical(
                "execution_emergency_close_failed", symbol=symbol, decision_id=str(decision_id), error=str(exc)
            )
            outcome = "failed"

        from database.session_factory import SessionFactory

        with SessionFactory.get_session() as session:
            EventLogRepository(session).record(
                event_type="execution_naked_position_emergency_close",
                entity_type="decision",
                entity_id=decision_id,
                payload={"symbol": symbol, "reason": reason, "outcome": outcome},
            )

    def get_open_position(self, symbol: str) -> dict | None:
        if not self.is_configured():
            return None
        return self._adapter.get_open_position(symbol)

    def get_order_status(self, symbol: str, order_id: str) -> OrderStatus | None:
        if not self.is_configured():
            return None
        return self._adapter.get_order_status(symbol, order_id)
