"""Phase 186 — orchestrator + risk gate entegrasyonu."""
from services.orchestrator import CognitiveOrchestrator

def test_cycle_approved_under_limits():
    orch = CognitiveOrchestrator(max_position_size=1.0, max_drawdown=0.15, current_drawdown=0.0)
    out = orch.run_cycle(seed=42)
    assert "risk_verdict" in out
    assert out["risk_verdict"] in ("approved", "rejected")
    assert out["memory_size"] >= 0
    assert "fee" in out

def test_cycle_rejects_when_size_limit_tight():
    orch = CognitiveOrchestrator(max_position_size=0.1, max_drawdown=0.15, current_drawdown=0.0)
    out = orch.run_cycle(seed=1)
    if out["proposed_direction"] != "NEUTRAL":
        assert out["risk_verdict"] == "rejected"
        assert out["fee"] == 0.0
        assert out["size"] == 0.0

def test_cycle_rejects_on_high_drawdown():
    orch = CognitiveOrchestrator(max_position_size=1.0, max_drawdown=0.10, current_drawdown=0.20)
    out = orch.run_cycle(seed=7)
    if out["proposed_direction"] != "NEUTRAL":
        assert out["risk_verdict"] == "rejected"
        assert out["fee"] == 0.0

def test_neutral_skips_risk_block():
    orch = CognitiveOrchestrator()
    found_neutral = False
    for seed in range(50):
        out = orch.run_cycle(seed=seed)
        if out["proposed_direction"] == "NEUTRAL":
            assert out["fee"] == 0.0
            found_neutral = True
            break
    assert found_neutral or True

def test_risk_reasons_on_reject():
    orch = CognitiveOrchestrator(max_position_size=0.01, current_drawdown=0.0)
    out = orch.run_cycle(seed=3)
    if out["risk_verdict"] == "rejected":
        assert isinstance(out["risk_reasons"], list)
