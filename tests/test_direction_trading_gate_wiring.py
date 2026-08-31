"""decision_recorder.py::record()'a wire edilen direction_trading_gate
entegrasyon testleri — kullanıcı isteği (2026-08-28). tests/test_mae_mfe_
bucket_gate_wiring.py'deki AYNI desen."""
import json
import uuid

from contracts.context import CognitiveCycleContext
from database.repositories.app_settings_repository import AppSettingsRepository
from database.session_factory import SessionFactory
from services.decision_recorder import DecisionRecorder


def _set_direction_map(mapping: dict) -> None:
    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set("direction_trading_enabled", json.dumps(mapping), updated_by="test")


def _reset_defaults() -> None:
    _set_direction_map({"LONG": True, "SHORT": True})


def _ctx(symbol: str, direction: str = "LONG") -> CognitiveCycleContext:
    return CognitiveCycleContext(
        market={
            "symbol": symbol,
            "raw_snapshot": {"close": 100.0},
            "features": {"trend": "bullish", "volatility_regime": "normal", "long_term_trend_regime": "bull_trend"},
        },
        decision={
            "proposed_direction": direction, "final_action": direction,
            "final_size": 10.0, "stop_loss_distance": 5.0, "take_profit_distance": 5.0,
        },
        risk={"evaluation": {"verdict": "approved"}},
    )


def test_short_disabled_blocks_a_short_entry():
    _reset_defaults()
    _set_direction_map({"LONG": True, "SHORT": False})
    symbol = f"DIRTEST{uuid.uuid4().hex[:6]}USDT"
    try:
        event = DecisionRecorder().record(_ctx(symbol, direction="SHORT"), [])
        assert event.status == "no_trade"

        gate_blocks = [o for o in event.agent_opinions if o.get("type") == "gate_block"]
        assert len(gate_blocks) == 1
        assert gate_blocks[0]["data"]["gate"] == "direction_trading_gate"
        assert gate_blocks[0]["data"]["direction"] == "SHORT"
    finally:
        _reset_defaults()


def test_short_disabled_does_not_block_long():
    _reset_defaults()
    _set_direction_map({"LONG": True, "SHORT": False})
    symbol = f"DIRTEST{uuid.uuid4().hex[:6]}USDT"
    try:
        event = DecisionRecorder().record(_ctx(symbol, direction="LONG"), [])
        assert event.status == "open"
    finally:
        _reset_defaults()


def test_both_enabled_by_default_is_not_blocked():
    _reset_defaults()
    symbol = f"DIRTEST{uuid.uuid4().hex[:6]}USDT"
    event = DecisionRecorder().record(_ctx(symbol, direction="SHORT"), [])
    assert event.status == "open"
