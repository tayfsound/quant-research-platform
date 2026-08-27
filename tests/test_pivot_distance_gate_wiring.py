"""Faz 366-devam — backlog #17. decision_recorder.py::record()'a wire
edilen Pivot-Mesafe Kapısı entegrasyon testleri. tests/test_decision_
recorder.py'deki pyramid_regime_gate testleriyle AYNI desen."""
from contracts.context import CognitiveCycleContext
from database.repositories.app_settings_repository import AppSettingsRepository
from database.session_factory import SessionFactory
from services.decision_recorder import DecisionRecorder

# services/agent_memory.py::_CRYPTO_LARGE_CAP_SYMBOLS içinde gerçek bir sembol.
_LARGE_CAP_SYMBOL = "BTCUSDT"
_SMALL_CAP_SYMBOL = "OBSCURUSDT"


def _set_gate(enabled: str = "true", threshold: str = "0.006") -> None:
    with SessionFactory.get_session() as session:
        repo = AppSettingsRepository(session)
        repo.set("pivot_distance_gate_enabled", enabled, updated_by="test")
        repo.set("pivot_distance_gate_threshold_pct", threshold, updated_by="test")


def _ctx(symbol: str, distance_pct: float | None) -> CognitiveCycleContext:
    return CognitiveCycleContext(
        market={
            "symbol": symbol,
            "raw_snapshot": {"close": 100.0},
            "features": {"nearest_pivot_distance_pct": distance_pct},
        },
        decision={
            "proposed_direction": "LONG", "final_action": "LONG",
            "final_size": 10.0, "stop_loss_distance": 5.0, "take_profit_distance": 5.0,
        },
        risk={"evaluation": {"verdict": "approved"}},
    )


def test_large_cap_far_from_pivot_is_blocked():
    _set_gate()
    recorder = DecisionRecorder()
    event = recorder.record(_ctx(_LARGE_CAP_SYMBOL, distance_pct=0.02), [])
    assert event.status == "no_trade"


def test_large_cap_near_pivot_is_not_blocked():
    _set_gate()
    recorder = DecisionRecorder()
    event = recorder.record(_ctx(_LARGE_CAP_SYMBOL, distance_pct=0.001), [])
    assert event.status == "open"


def test_small_cap_far_from_pivot_is_not_blocked():
    """Gerçek veri small-cap'te desenin TERS/YOK olduğunu gösterdi —
    gate SADECE large-cap'e uygulanmalı."""
    _set_gate()
    recorder = DecisionRecorder()
    event = recorder.record(_ctx(_SMALL_CAP_SYMBOL, distance_pct=0.02), [])
    assert event.status == "open"


def test_missing_distance_is_not_blocked():
    _set_gate()
    recorder = DecisionRecorder()
    event = recorder.record(_ctx(_LARGE_CAP_SYMBOL, distance_pct=None), [])
    assert event.status == "open"


def test_gate_is_a_noop_when_disabled():
    _set_gate(enabled="false")
    try:
        recorder = DecisionRecorder()
        event = recorder.record(_ctx(_LARGE_CAP_SYMBOL, distance_pct=0.02), [])
        assert event.status == "open"
    finally:
        _set_gate(enabled="true")
