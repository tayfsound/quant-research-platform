"""Kullanıcı isteği (2026-08-31): decision_recorder.py'deki 7 kapı
(strategy_regime/signal_persistence/pivot_distance/mae_mfe_bucket/
regime_trading/direction_trading/asset_class_trading) hiçbir açıklama
bırakmadan sessizce engelliyordu — "neden açılmadı" sorusu DB'yi elle
kazmadan cevaplanamıyordu. signal_persistence/pivot_distance/mae_mfe_
bucket/direction_trading'in kendi wiring dosyalarına gate_block
doğrulaması eklendi (bkz. o dosyalar). Bu dosya, dedike bir wiring
testi OLMAYAN kalan üçünü (strategy_regime/regime_trading/asset_class_
trading) kapsıyor."""
import json
import uuid

from contracts.context import CognitiveCycleContext
from contracts.strategy_gate_approval import StrategyGateApproval
from database.repositories.app_settings_repository import AppSettingsRepository
from database.repositories.strategy_gate_approval_repository import StrategyGateApprovalRepository
from database.session_factory import SessionFactory
from services.decision_recorder import DecisionRecorder

_TEST_TREND = "testregime"
_TEST_VOL = "gateblockvisibility"
_TEST_REGIME = f"{_TEST_TREND}_{_TEST_VOL}"


def _ctx(symbol: str, direction: str = "LONG", trend: str = "bullish", volatility_regime: str = "normal") -> CognitiveCycleContext:
    return CognitiveCycleContext(
        market={
            "symbol": symbol,
            "raw_snapshot": {"close": 100.0},
            "features": {"trend": trend, "volatility_regime": volatility_regime},
        },
        decision={
            "proposed_direction": direction, "final_action": direction,
            "final_size": 10.0, "stop_loss_distance": 5.0, "take_profit_distance": 5.0,
        },
        risk={"evaluation": {"verdict": "approved"}},
    )


def test_strategy_regime_gate_logs_a_gate_block():
    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set("strategy_gate_enabled", "true", updated_by="test")
        StrategyGateApprovalRepository(session).save(
            StrategyGateApproval(
                strategy="ai_council_LONG_swing", market_regime=_TEST_REGIME,
                sample_size=50, win_rate=0.3, rest_win_rate=0.8, delta_vs_rest=-0.5,
                p_value=0.0, replicated_out_of_sample=True, status="blocked", approved_by="test",
            )
        )

    symbol = f"SRGTEST{uuid.uuid4().hex[:6]}USDT"
    event = DecisionRecorder().record(_ctx(symbol, trend=_TEST_TREND, volatility_regime=_TEST_VOL), [])
    assert event.status == "no_trade"
    gate_blocks = [o for o in event.agent_opinions if o.get("type") == "gate_block"]
    assert len(gate_blocks) == 1
    assert gate_blocks[0]["data"]["gate"] == "strategy_regime_gate"
    assert gate_blocks[0]["data"]["strategy_label"] == "ai_council_LONG_swing"
    assert gate_blocks[0]["data"]["market_regime"] == _TEST_REGIME


def test_regime_trading_gate_logs_a_gate_block():
    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set(
            "regime_trading_enabled",
            json.dumps({"bullish_high": False, "bullish_normal": True, "bullish_low": True,
                        "bearish_high": True, "bearish_normal": True, "bearish_low": True}),
            updated_by="test",
        )
    try:
        symbol = f"RTGTEST{uuid.uuid4().hex[:6]}USDT"
        event = DecisionRecorder().record(_ctx(symbol, trend="bullish", volatility_regime="high"), [])
        assert event.status == "no_trade"
        gate_blocks = [o for o in event.agent_opinions if o.get("type") == "gate_block"]
        assert len(gate_blocks) == 1
        assert gate_blocks[0]["data"]["gate"] == "regime_trading_gate"
        assert gate_blocks[0]["data"]["market_regime"] == "bullish_high"
    finally:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set(
                "regime_trading_enabled",
                json.dumps({"bullish_high": True, "bullish_normal": True, "bullish_low": True,
                            "bearish_high": True, "bearish_normal": True, "bearish_low": True}),
                updated_by="test",
            )


def test_asset_class_trading_gate_logs_a_gate_block():
    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set(
            "asset_class_trading_enabled",
            json.dumps({"crypto": False, "commodity": True, "equity": True}),
            updated_by="test",
        )
    try:
        symbol = f"ACTTEST{uuid.uuid4().hex[:6]}USDT"
        event = DecisionRecorder().record(_ctx(symbol), [])
        assert event.status == "no_trade"
        gate_blocks = [o for o in event.agent_opinions if o.get("type") == "gate_block"]
        assert len(gate_blocks) == 1
        assert gate_blocks[0]["data"]["gate"] == "asset_class_trading_gate"
        assert gate_blocks[0]["data"]["asset_class"] == "crypto"
    finally:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set(
                "asset_class_trading_enabled",
                json.dumps({"crypto": True, "commodity": True, "equity": True}),
                updated_by="test",
            )
