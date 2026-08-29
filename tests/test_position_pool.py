"""Faz 350 — Pozisyon Havuzu / Max Confidence Modu testleri.

bkz. services/position_pool.py, database/repositories/position_pool_repository.py,
services/decision_recorder.py (çağrı noktası)."""
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import text

from contracts.context import CognitiveCycleContext
from database.repositories.app_settings_repository import AppSettingsRepository
from database.repositories.position_pool_repository import (
    PositionPoolCandidateModel,
    PositionPoolRepository,
)
from database.session_factory import SessionFactory
from services.decision_recorder import DecisionRecorder
from services.position_pool import resolve_due_pool_windows, try_pool_candidate


def _cleanup(symbol: str) -> None:
    with SessionFactory.get_session() as session:
        session.execute(text("DELETE FROM decisions WHERE symbol = :symbol"), {"symbol": symbol})
        session.execute(text("DELETE FROM position_pool_candidates WHERE symbol = :symbol"), {"symbol": symbol})
        session.commit()


def _set_pool_settings(**overrides) -> None:
    defaults = {
        "max_confidence_mode_enabled": "false",
        "max_confidence_mode_pool_window_minutes": "15",
        "max_confidence_mode_top_k": "3",
    }
    defaults.update(overrides)
    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        for key, value in defaults.items():
            repo.set(key, value, updated_by="test")


def _ctx(symbol, direction="LONG", confidence=0.8, final_size=0.5, entry_price=100.0):
    ctx = CognitiveCycleContext(
        market={"symbol": symbol, "raw_snapshot": {"close": entry_price}},
        decision={
            "proposed_direction": direction, "final_action": direction,
            "final_size": final_size, "confidence": confidence,
            "stop_loss_distance": 5.0, "take_profit_distance": 10.0,
        },
        risk={"evaluation": {"verdict": "approved"}},
    )
    return ctx


def _add_candidate(symbol, confidence, window_closes_at, direction="LONG", status="pending") -> PositionPoolCandidateModel:
    row = PositionPoolCandidateModel(
        id=uuid4(), symbol=symbol, direction=direction, confidence=confidence,
        entry_price_at_pool=100.0, stop_loss_distance=5.0, take_profit_distance=10.0,
        planned_notional_usd=50.0, leverage=1.0,
        pooled_at=datetime.now(UTC) - timedelta(minutes=20),
        window_closes_at=window_closes_at, status=status,
    )
    with SessionFactory.get_session() as session:
        PositionPoolRepository(session).add(row)
    return row


def test_try_pool_candidate_is_a_noop_when_disabled():
    symbol = f"POOLTEST{uuid4().hex[:8]}"
    try:
        _set_pool_settings(max_confidence_mode_enabled="false")
        pooled = try_pool_candidate(
            _ctx(symbol), "LONG", 100.0, weight_snapshot_id=None, belief_snapshot_id=None,
        )
        assert pooled is False
        with SessionFactory.get_session() as session:
            count = session.execute(
                text("SELECT count(*) FROM position_pool_candidates WHERE symbol = :s"), {"s": symbol}
            ).scalar()
        assert count == 0
    finally:
        _cleanup(symbol)


def test_try_pool_candidate_saves_row_when_enabled():
    symbol = f"POOLTEST{uuid4().hex[:8]}"
    try:
        _set_pool_settings(max_confidence_mode_enabled="true", max_confidence_mode_pool_window_minutes="15")
        pooled = try_pool_candidate(
            _ctx(symbol, direction="SHORT", confidence=0.77, final_size=0.5, entry_price=200.0),
            "SHORT", 200.0, weight_snapshot_id=None, belief_snapshot_id=None,
        )
        assert pooled is True
        with SessionFactory.get_session() as session:
            row = session.execute(
                text("SELECT direction, confidence, planned_notional_usd, status FROM position_pool_candidates WHERE symbol = :s"),
                {"s": symbol},
            ).fetchone()
        assert row.direction == "SHORT"
        assert abs(row.confidence - 0.77) < 1e-9
        assert abs(row.planned_notional_usd - 100.0) < 1e-9  # 0.5 * 200.0
        assert row.status == "pending"
    finally:
        _cleanup(symbol)
        _set_pool_settings(max_confidence_mode_enabled="false")


def test_try_pool_candidate_fails_open_when_stop_target_missing():
    """Gerekli veriler eksikse (ör. stop/hedef mesafesi None) havuzlamak
    yerine False dönmeli — çağıran taraf normal açılış akışına devam
    etsin, sessizce eksik bir aday kaydedilmesin."""
    symbol = f"POOLTEST{uuid4().hex[:8]}"
    try:
        _set_pool_settings(max_confidence_mode_enabled="true")
        ctx = CognitiveCycleContext(
            market={"symbol": symbol, "raw_snapshot": {"close": 100.0}},
            decision={"proposed_direction": "LONG", "final_action": "LONG", "final_size": 0.5},
            risk={"evaluation": {"verdict": "approved"}},
        )
        pooled = try_pool_candidate(ctx, "LONG", 100.0, weight_snapshot_id=None, belief_snapshot_id=None)
        assert pooled is False
    finally:
        _cleanup(symbol)
        _set_pool_settings(max_confidence_mode_enabled="false")


def test_decision_recorder_pools_instead_of_opening_when_enabled():
    symbol = f"POOLTEST{uuid4().hex[:8]}"
    try:
        _set_pool_settings(max_confidence_mode_enabled="true")
        recorder = DecisionRecorder()
        event = recorder.record(_ctx(symbol, direction="LONG", confidence=0.9), [])

        assert event.status == "no_trade"
        assert event.entry_price is None
        with SessionFactory.get_session() as session:
            count = session.execute(
                text("SELECT count(*) FROM position_pool_candidates WHERE symbol = :s"), {"s": symbol}
            ).scalar()
        assert count == 1
    finally:
        _cleanup(symbol)
        _set_pool_settings(max_confidence_mode_enabled="false")


def test_decision_recorder_opens_normally_when_pooling_disabled():
    """Regresyon kilidi: max_confidence_mode_enabled=false (varsayılan)
    iken davranış birebir eskisiyle aynı — hemen açılır, hiç havuzlanmaz."""
    symbol = f"POOLTEST{uuid4().hex[:8]}"
    try:
        _set_pool_settings(max_confidence_mode_enabled="false")
        recorder = DecisionRecorder()
        event = recorder.record(_ctx(symbol, direction="LONG", confidence=0.9), [])

        assert event.status == "open"
        assert event.entry_price == 100.0
        with SessionFactory.get_session() as session:
            count = session.execute(
                text("SELECT count(*) FROM position_pool_candidates WHERE symbol = :s"), {"s": symbol}
            ).scalar()
        assert count == 0
    finally:
        _cleanup(symbol)


def test_resolve_due_pool_windows_selects_top_k_by_confidence(monkeypatch):
    monkeypatch.setattr("services.position_pool._fresh_price", lambda symbol: 100.0)
    monkeypatch.setattr("services.position_pool._risk_headroom_ok", lambda symbol: True)

    symbols = [f"POOLTEST{uuid4().hex[:8]}" for _ in range(4)]
    confidences = [0.5, 0.9, 0.6, 0.95]
    due_at = datetime.now(UTC) - timedelta(seconds=1)
    try:
        _set_pool_settings(max_confidence_mode_enabled="true", max_confidence_mode_top_k="2")
        for symbol, conf in zip(symbols, confidences):
            _add_candidate(symbol, conf, due_at)

        result = resolve_due_pool_windows()

        assert result["due"] == 4
        assert result["selected"] == 2
        assert result["opened"] == 2
        assert result["rejected"] == 2

        with SessionFactory.get_session() as session:
            statuses = {
                row.symbol: row.status
                for row in session.execute(
                    text("SELECT symbol, status FROM position_pool_candidates WHERE symbol = ANY(:syms)"),
                    {"syms": symbols},
                )
            }
        # En yüksek iki confidence (0.95, 0.9) selected, geri kalanı rejected.
        assert statuses[symbols[3]] == "selected"  # 0.95
        assert statuses[symbols[1]] == "selected"  # 0.9
        assert statuses[symbols[0]] == "rejected"  # 0.5
        assert statuses[symbols[2]] == "rejected"  # 0.6

        with SessionFactory.get_session() as session:
            opened = session.execute(
                text("SELECT count(*) FROM decisions WHERE symbol = ANY(:syms) AND status = 'open'"),
                {"syms": symbols},
            ).scalar()
        assert opened == 2
    finally:
        for symbol in symbols:
            _cleanup(symbol)
        _set_pool_settings(max_confidence_mode_enabled="false")


def test_resolve_due_pool_windows_opens_at_fresh_price_not_pool_time_price(monkeypatch):
    """Havuzun tüm amacı bu: fiyat pool anından SONRA değişmiş olsa bile,
    seçilen aday pool anındaki DEĞİL, seçim anındaki gerçek fiyattan açılır."""
    monkeypatch.setattr("services.position_pool._fresh_price", lambda symbol: 250.0)
    monkeypatch.setattr("services.position_pool._risk_headroom_ok", lambda symbol: True)

    symbol = f"POOLTEST{uuid4().hex[:8]}"
    due_at = datetime.now(UTC) - timedelta(seconds=1)
    try:
        _set_pool_settings(max_confidence_mode_enabled="true", max_confidence_mode_top_k="3")
        _add_candidate(symbol, confidence=0.9, window_closes_at=due_at, direction="LONG")

        result = resolve_due_pool_windows()
        assert result["opened"] == 1

        with SessionFactory.get_session() as session:
            row = session.execute(
                text("SELECT entry_price, stop_loss_price, take_profit_price, quantity FROM decisions WHERE symbol = :s AND status = 'open'"),
                {"s": symbol},
            ).fetchone()
        assert row.entry_price == 250.0  # pool anındaki 100.0 DEĞİL
        assert row.stop_loss_price == 245.0  # 250 - 5.0 (stop_loss_distance)
        assert row.take_profit_price == 260.0  # 250 + 10.0 (take_profit_distance)
        assert abs(row.quantity - (50.0 / 250.0)) < 1e-9  # planned_notional_usd / fresh_price
    finally:
        _cleanup(symbol)
        _set_pool_settings(max_confidence_mode_enabled="false")


def test_resolve_due_pool_windows_marks_failed_when_risk_headroom_gone(monkeypatch):
    monkeypatch.setattr("services.position_pool._fresh_price", lambda symbol: 100.0)
    monkeypatch.setattr("services.position_pool._risk_headroom_ok", lambda symbol: False)

    symbol = f"POOLTEST{uuid4().hex[:8]}"
    due_at = datetime.now(UTC) - timedelta(seconds=1)
    try:
        _set_pool_settings(max_confidence_mode_enabled="true", max_confidence_mode_top_k="3")
        _add_candidate(symbol, confidence=0.9, window_closes_at=due_at)

        result = resolve_due_pool_windows()
        assert result["opened"] == 0
        assert result["failed"] == 1

        with SessionFactory.get_session() as session:
            opened = session.execute(
                text("SELECT count(*) FROM decisions WHERE symbol = :s"), {"s": symbol}
            ).scalar()
        assert opened == 0
    finally:
        _cleanup(symbol)
        _set_pool_settings(max_confidence_mode_enabled="false")


def test_resolve_due_pool_windows_uses_real_execution_service_when_symbol_is_testnet(monkeypatch):
    """Faz 370-devam — KRİTİK canlı bulgu regresyon testi (kullanıcı:
    "canlıda işlem almamış, test modunda almış sadece"): resolve_due_
    pool_windows() önceden ExecutionService'i hiç çağırmıyordu — havuzdan
    açılan HER pozisyon, execution_mode_symbols'ta "testnet" işaretli bir
    sembol bile olsa sessizce simüle ediliyordu. max_confidence_mode_
    enabled=true iken (üretimde şu an öyle) bu, GERÇEK borsaya hiç emir
    gitmemesi demekti. Artık gerçekten çağrılıyor mu ve dolum sonucu
    (entry_price/quantity/exchange_order_id) gerçekten kullanılıyor mu
    doğrulanıyor."""
    from services.execution_service import OpenPositionResult

    class _FakeExecutionService:
        calls = []

        def is_configured(self) -> bool:
            return True

        def open_position(self, **kwargs):
            _FakeExecutionService.calls.append(kwargs)
            return OpenPositionResult(
                entry_price=101.5, executed_qty=0.4931,
                exchange_order_id="9001", exchange_client_order_id="pool-1",
                exchange_stop_order_id="9002", exchange_tp_order_id="9003",
            )

    monkeypatch.setattr("services.execution_service.ExecutionService", _FakeExecutionService)
    monkeypatch.setattr("services.position_pool._fresh_price", lambda symbol: 100.0)
    monkeypatch.setattr("services.position_pool._risk_headroom_ok", lambda symbol: True)

    symbol = f"POOLTEST{uuid4().hex[:8]}"
    due_at = datetime.now(UTC) - timedelta(seconds=1)
    try:
        with SessionFactory.get_session() as session:
            repo = AppSettingsRepository(session)
            mapping = json.loads(repo.get("execution_mode_symbols") or "{}")
            mapping[symbol] = "testnet"
            repo.set("execution_mode_symbols", json.dumps(mapping), updated_by="test")

        _set_pool_settings(max_confidence_mode_enabled="true", max_confidence_mode_top_k="3")
        _add_candidate(symbol, confidence=0.9, window_closes_at=due_at, direction="LONG")

        result = resolve_due_pool_windows()
        assert result["opened"] == 1
        assert len(_FakeExecutionService.calls) == 1
        assert _FakeExecutionService.calls[0]["symbol"] == symbol

        with SessionFactory.get_session() as session:
            row = session.execute(
                text(
                    "SELECT execution_mode, entry_price, quantity, exchange_order_id "
                    "FROM decisions WHERE symbol = :s AND status = 'open'"
                ),
                {"s": symbol},
            ).fetchone()
        assert row.execution_mode == "testnet"
        assert row.entry_price == 101.5  # ExecutionService'in GERÇEK dolum fiyatı, 100.0 (fresh_price) DEĞİL
        assert abs(row.quantity - 0.4931) < 1e-9
        assert row.exchange_order_id == "9001"
    finally:
        _cleanup(symbol)
        _set_pool_settings(max_confidence_mode_enabled="false")
        with SessionFactory.get_session() as session:
            repo = AppSettingsRepository(session)
            mapping = json.loads(repo.get("execution_mode_symbols") or "{}")
            mapping.pop(symbol, None)
            repo.set("execution_mode_symbols", json.dumps(mapping), updated_by="test")


def test_resolve_due_pool_windows_ignores_candidates_still_within_window(monkeypatch):
    monkeypatch.setattr("services.position_pool._fresh_price", lambda symbol: 100.0)
    monkeypatch.setattr("services.position_pool._risk_headroom_ok", lambda symbol: True)

    symbol = f"POOLTEST{uuid4().hex[:8]}"
    not_due_yet = datetime.now(UTC) + timedelta(minutes=10)
    try:
        _set_pool_settings(max_confidence_mode_enabled="true")
        _add_candidate(symbol, confidence=0.9, window_closes_at=not_due_yet)

        result = resolve_due_pool_windows()
        assert result == {"due": 0, "selected": 0, "rejected": 0, "failed": 0}

        with SessionFactory.get_session() as session:
            status = session.execute(
                text("SELECT status FROM position_pool_candidates WHERE symbol = :s"), {"s": symbol}
            ).scalar()
        assert status == "pending"
    finally:
        _cleanup(symbol)
        _set_pool_settings(max_confidence_mode_enabled="false")
