"""Faz 367-devam — decision_recorder.py::record()'a wire edilen MAE/MFE
Kova Trading Gate entegrasyon testleri. tests/test_asset_class_and_
regime_gate_wiring.py'deki AYNI desen."""
import json
import uuid

from contracts.context import CognitiveCycleContext
from database.repositories.app_settings_repository import AppSettingsRepository
from database.session_factory import SessionFactory
from services.decision_recorder import DecisionRecorder


def _set_bucket_map(mapping: dict) -> None:
    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set("mae_mfe_bucket_trading_enabled", json.dumps(mapping), updated_by="test")


def _reset_defaults() -> None:
    _set_bucket_map({})


def _ctx(symbol: str, direction: str = "LONG", regime: str = "bull_trend", volatility_regime: str = "normal") -> CognitiveCycleContext:
    return CognitiveCycleContext(
        market={
            "symbol": symbol,
            "raw_snapshot": {"close": 100.0},
            "features": {
                "trend": "bullish", "volatility_regime": volatility_regime,
                "long_term_trend_regime": regime,
            },
        },
        decision={
            "proposed_direction": direction, "final_action": direction,
            "final_size": 10.0, "stop_loss_distance": 5.0, "take_profit_distance": 5.0,
        },
        risk={"evaluation": {"verdict": "approved"}},
    )


def test_bucket_disabled_blocks_a_matching_entry():
    _reset_defaults()
    _set_bucket_map({"direction=LONG|regime=bull_trend|volatility_regime=normal|asset_class=crypto": False})
    symbol = f"MMTEST{uuid.uuid4().hex[:6]}USDT"
    try:
        event = DecisionRecorder().record(_ctx(symbol), [])
        assert event.status == "no_trade"
    finally:
        _reset_defaults()


def test_bucket_not_in_map_is_not_blocked():
    """Fail-open: enabled_map boşken (varsayılan) hiçbir kova engellenmez."""
    _reset_defaults()
    symbol = f"MMTEST{uuid.uuid4().hex[:6]}USDT"
    event = DecisionRecorder().record(_ctx(symbol), [])
    assert event.status == "open"


def test_different_direction_in_same_regime_is_not_blocked():
    """LONG kapalıyken AYNI rejim/volatilitedeki SHORT etkilenmemeli —
    kova anahtarı direction'ı da içeriyor."""
    _reset_defaults()
    _set_bucket_map({"direction=LONG|regime=bull_trend|volatility_regime=normal|asset_class=crypto": False})
    symbol = f"MMTEST{uuid.uuid4().hex[:6]}USDT"
    try:
        event = DecisionRecorder().record(_ctx(symbol, direction="SHORT"), [])
        assert event.status == "open"
    finally:
        _reset_defaults()


def test_different_volatility_regime_is_not_blocked():
    _reset_defaults()
    _set_bucket_map({"direction=LONG|regime=bull_trend|volatility_regime=normal|asset_class=crypto": False})
    symbol = f"MMTEST{uuid.uuid4().hex[:6]}USDT"
    try:
        event = DecisionRecorder().record(_ctx(symbol, volatility_regime="high"), [])
        assert event.status == "open"
    finally:
        _reset_defaults()


def test_bucket_explicitly_enabled_does_not_block():
    _reset_defaults()
    _set_bucket_map({"direction=LONG|regime=bull_trend|volatility_regime=normal|asset_class=crypto": True})
    symbol = f"MMTEST{uuid.uuid4().hex[:6]}USDT"
    try:
        event = DecisionRecorder().record(_ctx(symbol), [])
        assert event.status == "open"
    finally:
        _reset_defaults()
