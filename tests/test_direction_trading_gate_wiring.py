"""decision_recorder.py::record()'a wire edilen direction_trading_gate
entegrasyon testleri — kullanıcı isteği (2026-08-28). tests/test_mae_mfe_
bucket_gate_wiring.py'deki AYNI desen."""
import json
import uuid

import pytest

from contracts.context import CognitiveCycleContext
from database.repositories.app_settings_repository import AppSettingsRepository
from database.session_factory import SessionFactory
from services.decision_recorder import DecisionRecorder
from tests.live_gate_helpers import global_real_exchange_mode


@pytest.fixture(autouse=True)
def _gates_run_in_live_mode():
    """Faz 482 — bu dosyadaki testlerin HEPSİ "kapı canlıda gerçekten
    engelliyor mu" sorusunu test ediyor. Kapılar artık sadece gerçek
    borsaya giden (live/testnet) sembollerde engelliyor; global
    execution_mode varsayılanı "simulated" olduğu için işaretlenmemiş
    her test sembolü carve-out'a düşerdi. Bkz. tests/live_gate_helpers.py.
    """
    with global_real_exchange_mode():
        yield



def _set_direction_map(mapping: dict) -> None:
    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set("direction_trading_enabled", json.dumps(mapping), updated_by="test")


def _reset_defaults() -> None:
    _set_direction_map({"LONG": True, "SHORT": True})


def _ctx(symbol: str, direction: str = "LONG") -> CognitiveCycleContext:
    # Faz 426 — stop_loss_distance 5.0'dan 3.0'a düşürüldü (%5 -> %3):
    # bu dosya SADECE direction_trading_gate'i izole test ediyor, %5
    # (swing) yeni short_scalp_only_gate'i (varsayılan AÇIK) SHORT
    # testlerinde ONDAN ÖNCE tetikleyip yanlış gate_block nedeni
    # raporlardı — min_confidence_gate için Faz 421'de uygulanan AYNI
    # düzeltme deseni (bkz. test_silent_gates_gate_block_visibility.py).
    return CognitiveCycleContext(
        market={
            "symbol": symbol,
            "raw_snapshot": {"close": 100.0},
            "features": {"trend": "bullish", "volatility_regime": "normal", "long_term_trend_regime": "bull_trend"},
        },
        decision={
            "proposed_direction": direction, "final_action": direction,
            "final_size": 10.0, "stop_loss_distance": 3.0, "take_profit_distance": 3.0,
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
