"""Faz 315 — Execution Layer, Faz 1: DecisionRecorder'ın execution_mode
bağlantısı. Sahte ExecutionService enjekte edilerek gerçek ağ/anahtar
gerektirmeden — ama gerçek DB'ye (quantdb_test) yazan tam yaşam
döngüsüyle doğrulanır (mevcut test_position_lifecycle.py deseniyle
aynı)."""
import json
import uuid
from unittest.mock import patch

from database.repositories.app_settings_repository import AppSettingsRepository
from database.repositories.decision_persistor import DecisionPersistor
from database.session_factory import SessionFactory
from services.execution_service import OpenPositionResult


class _FakeExecutionServiceConfigured:
    def __init__(self, open_position_result):
        self._result = open_position_result
        self.open_position_calls = []

    def is_configured(self) -> bool:
        return True

    def open_position(self, **kwargs):
        self.open_position_calls.append(kwargs)
        return self._result


class _RaisingExecutionService:
    """open_position hiç çağrılmamalıysa (varsayılan simulated mod)
    çağrılırsa test anında AssertionError ile başarısız olur."""

    def is_configured(self) -> bool:
        return True

    def open_position(self, **kwargs):
        raise AssertionError("execution_service.open_position simulated modda ASLA çağrılmamalı")


def _make_ctx(symbol, direction="LONG", final_size=0.3, filled_price=100.0, stop_loss=5.0, take_profit=10.0):
    from contracts.context import CognitiveCycleContext

    ctx = CognitiveCycleContext()
    ctx.market.symbol = symbol
    ctx.decision.proposed_direction = direction
    ctx.decision.final_size = final_size
    ctx.decision.filled_price = filled_price
    ctx.decision.stop_loss_distance = stop_loss
    ctx.decision.take_profit_distance = take_profit
    ctx.risk.evaluation.verdict = "approved"
    return ctx


def test_default_simulated_mode_never_calls_execution_service():
    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        from services.decision_recorder import DecisionRecorder

        symbol = f"EXECSIM{uuid.uuid4().hex[:8]}"
        ctx = _make_ctx(symbol)

        DecisionRecorder(execution_service=_RaisingExecutionService()).record(ctx)

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(ctx.cycle_id))
    assert row["status"] == "open"
    assert row["execution_mode"] == "simulated"


def test_testnet_mode_uses_real_fill_price_and_quantity_from_execution_service():
    symbol = f"EXECTN{uuid.uuid4().hex[:8]}"
    try:
        with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
            from services.decision_recorder import DecisionRecorder

            ctx = _make_ctx(symbol, filled_price=100.0)

            exec_result = OpenPositionResult(
                entry_price=100.25, executed_qty=0.29,
                exchange_order_id="1001", exchange_client_order_id="qrpe1",
                exchange_stop_order_id="1002", exchange_tp_order_id="1003",
            )
            fake_service = _FakeExecutionServiceConfigured(exec_result)

            recorder = DecisionRecorder(execution_service=fake_service)
            with patch.object(recorder, "_resolve_execution_mode", return_value="testnet"):
                recorder.record(ctx)

        assert len(fake_service.open_position_calls) == 1
        call = fake_service.open_position_calls[0]
        assert call["symbol"] == symbol
        assert call["direction"] == "LONG"

        with SessionFactory.get_session() as session:
            row = DecisionPersistor(session).get_by_id(str(ctx.cycle_id))
        assert row["status"] == "open"
        assert row["execution_mode"] == "testnet"
        assert row["entry_price"] == 100.25
        assert row["quantity"] == 0.29
        assert row["exchange_order_id"] == "1001"
        assert row["exchange_client_order_id"] == "qrpe1"
        assert row["exchange_stop_order_id"] == "1002"
        assert row["exchange_tp_order_id"] == "1003"
    finally:
        # Faz 363 — kritik bulgu: bu testin bıraktığı execution_mode=
        # 'testnet', status='open' kaydı TEMİZLENMİYORDU — paylaşılan test
        # DB'sinde kalıcı kalıyordu. close_due_positions() gibi TÜM açık
        # pozisyonları tarayan (limit=None) başka testler bu "unutulmuş"
        # sembole rastlayınca, execution_mode='testnet' olduğu için GERÇEK
        # Binance testnet API'sine bağlanmaya çalışıyordu — sembol borsada
        # hiç var olmadığı için "Invalid symbol" hatasıyla patlıyordu
        # (canlıda yakalandı: tests/test_position_lifecycle.py +
        # tests/test_pump_fade_strategy.py'de 46 ilgisiz test başarısız
        # oluyordu). Diğer testlerde bu sorun yok çünkü onlar status=
        # 'no_trade'/execution_mode='simulated' bırakıyor.
        with SessionFactory.get_session() as session:
            from sqlalchemy import text
            session.execute(text("DELETE FROM decisions WHERE symbol = :symbol"), {"symbol": symbol})
            session.commit()


def test_testnet_mode_records_no_trade_when_execution_service_returns_none():
    """ExecutionService.open_position None dönerse (giriş dolmadı ya da
    koruma emirleri başarısız oldu, fail-closed) hiçbir zaman uydurma
    bir 'open' satırı yazılmamalı — dürüstçe no_trade."""

    class _FakeExecutionServiceFailed:
        def is_configured(self) -> bool:
            return True

        def open_position(self, **kwargs):
            return None

    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        from services.decision_recorder import DecisionRecorder

        symbol = f"EXECFAIL{uuid.uuid4().hex[:8]}"
        ctx = _make_ctx(symbol)

        recorder = DecisionRecorder(execution_service=_FakeExecutionServiceFailed())
        with patch.object(recorder, "_resolve_execution_mode", return_value="testnet"):
            recorder.record(ctx)

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(ctx.cycle_id))
    assert row["status"] == "no_trade"
    assert row["entry_price"] is None


def test_testnet_mode_falls_back_to_simulated_when_execution_service_not_configured():
    """resolved_execution_mode 'testnet' olsa bile is_configured() False
    ise (gerçek anahtar yok) fail-closed olarak simulated gibi davranır
    — asla yarım bir emir denemesi yapılmaz."""

    class _UnconfiguredExecutionService:
        def is_configured(self) -> bool:
            return False

        def open_position(self, **kwargs):
            raise AssertionError("is_configured() False iken open_position çağrılmamalı")

    with patch("transformers.AutoModel.from_pretrained"), patch("transformers.AutoTokenizer.from_pretrained"):
        from services.decision_recorder import DecisionRecorder

        symbol = f"EXECNOKEY{uuid.uuid4().hex[:8]}"
        ctx = _make_ctx(symbol)

        recorder = DecisionRecorder(execution_service=_UnconfiguredExecutionService())
        with patch.object(recorder, "_resolve_execution_mode", return_value="testnet"):
            recorder.record(ctx)

    with SessionFactory.get_session() as session:
        row = DecisionPersistor(session).get_by_id(str(ctx.cycle_id))
    assert row["status"] == "open"
    assert row["execution_mode"] == "simulated"


def test_resolve_execution_mode_per_symbol_override_takes_precedence_over_global():
    """_symbol_leverage ile AYNI desen: execution_mode_symbols haritasında
    sembol için açık bir mod varsa global execution_mode ayarını EZER."""
    from services.decision_recorder import DecisionRecorder

    symbol = f"EXECRESOLVE{uuid.uuid4().hex[:8]}"

    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        current = json.loads(repo.get("execution_mode_symbols") or "{}")
        current[symbol] = "testnet"
        repo.set("execution_mode_symbols", json.dumps(current), updated_by="test")

    try:
        recorder = DecisionRecorder()
        assert recorder._resolve_execution_mode(symbol) == "testnet"
        assert recorder._resolve_execution_mode(f"UNMAPPED{uuid.uuid4().hex[:8]}") == "simulated"
    finally:
        with SessionFactory.get_session() as session:
            repo = AppSettingsRepository(session)
            current = json.loads(repo.get("execution_mode_symbols") or "{}")
            current.pop(symbol, None)
            repo.set("execution_mode_symbols", json.dumps(current), updated_by="test")
