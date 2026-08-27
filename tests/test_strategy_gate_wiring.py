"""Faz 366 — decision_recorder.py::record()'a wire edilen Strategy Gate
entegrasyon testleri. tests/test_decision_recorder.py'deki pyramid_
regime_gate testleriyle AYNI desen."""
from datetime import UTC, datetime

from contracts.context import CognitiveCycleContext
from database.repositories.app_settings_repository import AppSettingsRepository
from database.repositories.strategy_gate_approval_repository import (
    StrategyGateApprovalModel,
    StrategyGateApprovalRepository,
)
from database.session_factory import SessionFactory
from services.decision_recorder import DecisionRecorder


def _set_strategy_gate_enabled(value: str = "true") -> None:
    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set("strategy_gate_enabled", value, updated_by="test")


def _block_pair(strategy: str, market_regime: str) -> str:
    from contracts.strategy_gate_approval import StrategyGateApproval

    with SessionFactory.get_session() as session:
        repo = StrategyGateApprovalRepository(session)
        approval = StrategyGateApproval(
            strategy=strategy, market_regime=market_regime,
            sample_size=100, win_rate=0.6, rest_win_rate=0.9, delta_vs_rest=-0.3, p_value=0.0,
            replicated_out_of_sample=True, status="blocked", approved_by="test",
        )
        repo.save(approval)
        return str(approval.id)


def _cleanup(approval_id: str) -> None:
    with SessionFactory.get_session() as session:
        session.query(StrategyGateApprovalModel).filter_by(id=approval_id).delete()
        session.commit()


def _long_swing_ctx(symbol: str) -> CognitiveCycleContext:
    return CognitiveCycleContext(
        market={
            "symbol": symbol,
            "raw_snapshot": {"close": 100.0},
            "features": {"trend": "bullish", "volatility_regime": "high"},
        },
        decision={
            "proposed_direction": "LONG", "final_action": "LONG",
            "final_size": 10.0, "stop_loss_distance": 5.0, "take_profit_distance": 5.0,
        },
        risk={"evaluation": {"verdict": "approved"}},
    )


def test_blocked_strategy_regime_pair_blocks_a_new_entry():
    _set_strategy_gate_enabled("true")
    approval_id = _block_pair("ai_council_LONG_swing", "bullish_high")
    symbol = f"SGTEST{__import__('uuid').uuid4().hex[:6]}USDT"
    recorder = DecisionRecorder()
    try:
        event = recorder.record(_long_swing_ctx(symbol), [])
        assert event.status == "no_trade"
    finally:
        _cleanup(approval_id)


def test_unblocked_strategy_regime_pair_does_not_block():
    _set_strategy_gate_enabled("true")
    symbol = f"SGTEST{__import__('uuid').uuid4().hex[:6]}USDT"
    recorder = DecisionRecorder()
    event = recorder.record(_long_swing_ctx(symbol), [])
    assert event.status == "open"


def test_gate_is_a_noop_when_disabled_even_with_a_blocked_pair():
    _set_strategy_gate_enabled("false")
    approval_id = _block_pair("ai_council_LONG_swing", "bullish_high")
    symbol = f"SGTEST{__import__('uuid').uuid4().hex[:6]}USDT"
    recorder = DecisionRecorder()
    try:
        event = recorder.record(_long_swing_ctx(symbol), [])
        assert event.status == "open"
    finally:
        _set_strategy_gate_enabled("true")
        _cleanup(approval_id)


def test_pending_pair_does_not_block_only_blocked_does():
    from contracts.strategy_gate_approval import StrategyGateApproval

    _set_strategy_gate_enabled("true")
    with SessionFactory.get_session() as session:
        repo = StrategyGateApprovalRepository(session)
        approval = StrategyGateApproval(
            strategy="ai_council_LONG_swing", market_regime="bullish_high",
            sample_size=100, win_rate=0.6, rest_win_rate=0.9, delta_vs_rest=-0.3, p_value=0.0,
            status="pending",
        )
        repo.save(approval)
        approval_id = str(approval.id)

    symbol = f"SGTEST{__import__('uuid').uuid4().hex[:6]}USDT"
    recorder = DecisionRecorder()
    try:
        event = recorder.record(_long_swing_ctx(symbol), [])
        assert event.status == "open"
    finally:
        _cleanup(approval_id)
