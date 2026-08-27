"""Faz 366-devam — decision_recorder.py::record()'a wire edilen Asset
Class / Regime Trading Gate entegrasyon testleri. tests/test_decision_
recorder.py'deki pyramid_regime_gate testleriyle AYNI desen."""
import json

from contracts.context import CognitiveCycleContext
from database.repositories.app_settings_repository import AppSettingsRepository
from database.session_factory import SessionFactory
from services.decision_recorder import DecisionRecorder


def _set_asset_class_map(mapping: dict) -> None:
    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set("asset_class_trading_enabled", json.dumps(mapping), updated_by="test")


def _set_regime_map(mapping: dict) -> None:
    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set("regime_trading_enabled", json.dumps(mapping), updated_by="test")


def _reset_defaults() -> None:
    _set_asset_class_map({"crypto": True, "commodity": True, "equity": True})
    _set_regime_map({
        "bullish_high": True, "bullish_normal": True, "bullish_low": True,
        "bearish_high": True, "bearish_normal": True, "bearish_low": True,
    })


def _ctx(symbol: str, trend: str = "bullish", volatility_regime: str = "normal") -> CognitiveCycleContext:
    return CognitiveCycleContext(
        market={
            "symbol": symbol,
            "raw_snapshot": {"close": 100.0},
            "features": {"trend": trend, "volatility_regime": volatility_regime},
        },
        decision={
            "proposed_direction": "LONG", "final_action": "LONG",
            "final_size": 10.0, "stop_loss_distance": 5.0, "take_profit_distance": 5.0,
        },
        risk={"evaluation": {"verdict": "approved"}},
    )


def test_crypto_trading_disabled_blocks_a_crypto_entry():
    _reset_defaults()
    _set_asset_class_map({"crypto": False, "commodity": True, "equity": True})
    symbol = f"ACTEST{__import__('uuid').uuid4().hex[:6]}USDT"
    try:
        event = DecisionRecorder().record(_ctx(symbol), [])
        assert event.status == "no_trade"
    finally:
        _reset_defaults()


def test_crypto_trading_enabled_does_not_block():
    _reset_defaults()
    symbol = f"ACTEST{__import__('uuid').uuid4().hex[:6]}USDT"
    event = DecisionRecorder().record(_ctx(symbol), [])
    assert event.status == "open"


def test_commodity_toggle_does_not_affect_crypto_symbol():
    _reset_defaults()
    _set_asset_class_map({"crypto": True, "commodity": False, "equity": True})
    symbol = f"ACTEST{__import__('uuid').uuid4().hex[:6]}USDT"
    try:
        event = DecisionRecorder().record(_ctx(symbol), [])
        assert event.status == "open"
    finally:
        _reset_defaults()


def test_unmapped_symbol_category_is_never_blocked():
    """"other" (hiçbir sınıfa girmeyen semboller) — kasıtlı olarak
    kapsam dışı, hiç engellenmez."""
    _reset_defaults()
    _set_asset_class_map({"crypto": False, "commodity": False, "equity": False})
    event = DecisionRecorder().record(_ctx("UNMAPPEDSYMBOL"), [])
    assert event.status == "open"
    _reset_defaults()


def test_regime_trading_disabled_blocks_matching_regime():
    _reset_defaults()
    _set_regime_map({
        "bullish_high": True, "bullish_normal": True, "bullish_low": True,
        "bearish_high": True, "bearish_normal": True, "bearish_low": False,
    })
    symbol = f"RGTEST{__import__('uuid').uuid4().hex[:6]}USDT"
    try:
        event = DecisionRecorder().record(_ctx(symbol, trend="bearish", volatility_regime="low"), [])
        assert event.status == "no_trade"
    finally:
        _reset_defaults()


def test_regime_trading_enabled_does_not_block():
    _reset_defaults()
    symbol = f"RGTEST{__import__('uuid').uuid4().hex[:6]}USDT"
    event = DecisionRecorder().record(_ctx(symbol, trend="bearish", volatility_regime="low"), [])
    assert event.status == "open"


def test_regime_toggle_for_a_different_regime_does_not_block():
    _reset_defaults()
    _set_regime_map({
        "bullish_high": True, "bullish_normal": True, "bullish_low": True,
        "bearish_high": True, "bearish_normal": True, "bearish_low": False,
    })
    symbol = f"RGTEST{__import__('uuid').uuid4().hex[:6]}USDT"
    try:
        event = DecisionRecorder().record(_ctx(symbol, trend="bullish", volatility_regime="high"), [])
        assert event.status == "open"
    finally:
        _reset_defaults()
