"""Agent Capability testleri — mod izolasyonu."""
from contracts.context import CognitiveCycleContext
from contracts.execution_mode import ExecutionMode, get_permission
from services.cognitive_engine import CognitiveEngine
from services.execution_router import ExecutionRouter


def test_experiment_mode_has_no_order_permission():
    p = get_permission(ExecutionMode.EXPERIMENT)
    assert p.can_place_orders is False
    assert p.can_access_exchange is False
    assert p.can_run_unlimited_experiments is True

def test_live_mode_cannot_modify_risk():
    p = get_permission(ExecutionMode.LIVE)
    assert p.can_modify_risk_limits is False

def test_experiment_mode_sandbox_execution():
    cognitive = CognitiveEngine()
    router = ExecutionRouter()
    ctx = CognitiveCycleContext(
        mode=ExecutionMode.EXPERIMENT,
        market={"symbol": "BTCUSDT", "timeframe": "4H", "features": {"price": 50000}},
        decision={"proposed_direction": "LONG", "proposed_size": 0.5},
    )
    ctx = cognitive.run(ctx)
    ctx = router.route(ctx)
    assert ctx.outcome["mode"] == "sandbox"
    assert ctx.outcome["executed"] is True
    assert "portfolio" in ctx.outcome

def test_paper_mode_is_sandbox():
    cognitive = CognitiveEngine()
    router = ExecutionRouter()
    ctx = CognitiveCycleContext(
        mode=ExecutionMode.PAPER,
        market={"symbol": "BTCUSDT", "timeframe": "4H", "features": {"price": 50000}},
        decision={"proposed_direction": "LONG", "proposed_size": 0.5},
    )
    ctx = cognitive.run(ctx)
    ctx = router.route(ctx)
    assert ctx.outcome["mode"] == "sandbox"
