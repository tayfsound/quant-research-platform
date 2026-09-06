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


def _ctx(
    symbol: str, direction: str = "LONG", trend: str = "bullish", volatility_regime: str = "normal",
    confidence: float = 0.9,
) -> CognitiveCycleContext:
    # Faz 421 — confidence varsayılan YÜKSEK (0.9): min_confidence_gate
    # artık varsayılan AÇIK (0.7 taban) — bu dosyadaki diğer testler
    # KENDİ gate'lerini izole test ediyor, confidence düşük kalırsa
    # (varsayılan 0.0) benim yeni kapım ONLARDAN ÖNCE bloke edip yanlış
    # gate_block nedeni raporlardı.
    return CognitiveCycleContext(
        market={
            "symbol": symbol,
            "raw_snapshot": {"close": 100.0},
            "features": {"trend": trend, "volatility_regime": volatility_regime},
        },
        decision={
            "proposed_direction": direction, "final_action": direction,
            "final_size": 10.0, "stop_loss_distance": 5.0, "take_profit_distance": 5.0,
            "confidence": confidence,
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


def test_regime_trading_gate_long_override_lets_long_through():
    """Faz 420 — kullanıcı bulgusu: bearish_normal'da LONG GÜÇLÜ kârlıydı
    (+$620,65, %88,9, n=225) SHORT aynı rejimde -$5.728 kaybediyordu.
    regime_trading_long_override'da olan bir rejimde LONG, rejim kapalı
    olsa bile açılabilmeli."""
    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set(
            "regime_trading_enabled",
            json.dumps({"bullish_high": True, "bullish_normal": True, "bullish_low": True,
                        "bearish_high": True, "bearish_normal": False, "bearish_low": True}),
            updated_by="test",
        )
        AppSettingsRepository(session).set(
            "regime_trading_long_override", json.dumps(["bearish_normal"]), updated_by="test",
        )
    try:
        symbol = f"RTGLOTEST{uuid.uuid4().hex[:6]}USDT"
        event = DecisionRecorder().record(_ctx(symbol, "LONG", trend="bearish", volatility_regime="normal"), [])
        gate_blocks = [o for o in event.agent_opinions if o.get("type") == "gate_block" and o["data"].get("gate") == "regime_trading_gate"]
        assert gate_blocks == []
    finally:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set(
                "regime_trading_enabled",
                json.dumps({"bullish_high": True, "bullish_normal": True, "bullish_low": True,
                            "bearish_high": True, "bearish_normal": True, "bearish_low": True}),
                updated_by="test",
            )
            AppSettingsRepository(session).set(
                "regime_trading_long_override", json.dumps(["bearish_normal"]), updated_by="test",
            )


def test_regime_trading_gate_long_override_does_not_help_short():
    """Aynı senaryoda SHORT hâlâ tam engelli kalmalı — override SADECE LONG."""
    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set(
            "regime_trading_enabled",
            json.dumps({"bullish_high": True, "bullish_normal": True, "bullish_low": True,
                        "bearish_high": True, "bearish_normal": False, "bearish_low": True}),
            updated_by="test",
        )
        AppSettingsRepository(session).set(
            "regime_trading_long_override", json.dumps(["bearish_normal"]), updated_by="test",
        )
    try:
        symbol = f"RTGLOSTEST{uuid.uuid4().hex[:6]}USDT"
        event = DecisionRecorder().record(_ctx(symbol, "SHORT", trend="bearish", volatility_regime="normal"), [])
        assert event.status == "no_trade"
        gate_blocks = [o for o in event.agent_opinions if o.get("type") == "gate_block" and o["data"].get("gate") == "regime_trading_gate"]
        assert len(gate_blocks) == 1
    finally:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set(
                "regime_trading_enabled",
                json.dumps({"bullish_high": True, "bullish_normal": True, "bullish_low": True,
                            "bearish_high": True, "bearish_normal": True, "bearish_low": True}),
                updated_by="test",
            )
            AppSettingsRepository(session).set(
                "regime_trading_long_override", json.dumps(["bearish_normal"]), updated_by="test",
            )


def test_min_confidence_gate_logs_a_gate_block():
    """Faz 421 — kullanıcı isteği: gerçek confidence kovası verisiyle
    LONG'da confidence≈0,7'nin hem yüksek kazanma oranı HEM gerçek
    pozitif PnL verdiği bulundu — bu tabanın altındaki kararlar
    engellenmeli."""
    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set("min_confidence_gate_enabled", "true", updated_by="test")
        AppSettingsRepository(session).set("min_confidence_gate_min_confidence", "0.7", updated_by="test")
    try:
        symbol = f"MCGTEST{uuid.uuid4().hex[:6]}USDT"
        event = DecisionRecorder().record(_ctx(symbol, confidence=0.5), [])
        assert event.status == "no_trade"
        gate_blocks = [o for o in event.agent_opinions if o.get("type") == "gate_block" and o["data"].get("gate") == "min_confidence_gate"]
        assert len(gate_blocks) == 1
        assert gate_blocks[0]["data"]["confidence"] == 0.5
        assert gate_blocks[0]["data"]["min_confidence"] == 0.7
    finally:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("min_confidence_gate_enabled", "false", updated_by="test")


def test_min_confidence_gate_lets_high_confidence_through():
    with SessionFactory.get_session() as session:
        AppSettingsRepository(session).set("min_confidence_gate_enabled", "true", updated_by="test")
        AppSettingsRepository(session).set("min_confidence_gate_min_confidence", "0.7", updated_by="test")
    try:
        symbol = f"MCGTEST{uuid.uuid4().hex[:6]}USDT"
        event = DecisionRecorder().record(_ctx(symbol, confidence=0.85), [])
        gate_blocks = [o for o in event.agent_opinions if o.get("type") == "gate_block" and o["data"].get("gate") == "min_confidence_gate"]
        assert gate_blocks == []
    finally:
        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set("min_confidence_gate_enabled", "false", updated_by="test")


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
