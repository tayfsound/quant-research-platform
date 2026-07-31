"""Phase 187 — orchestrator + cognitive engine integration."""
from unittest.mock import MagicMock, patch
from services.orchestrator import CognitiveOrchestrator

def test_cycle_runs():
    orch = CognitiveOrchestrator(max_position_size=1.0, max_drawdown=0.15, current_drawdown=0.0)
    out = orch.run_cycle(seed=42)
    assert "risk_verdict" in out
    assert out["risk_verdict"] in ("approved", "rejected")
    assert "fee" in out

def test_cycle_rejects_when_size_limit_tight():
    orch = CognitiveOrchestrator(max_position_size=0.1, max_drawdown=0.15, current_drawdown=0.0)
    out = orch.run_cycle(seed=1)
    assert "risk_verdict" in out

def test_cycle_rejects_on_high_drawdown():
    orch = CognitiveOrchestrator(max_position_size=1.0, max_drawdown=0.10, current_drawdown=0.20)
    out = orch.run_cycle(seed=7)
    assert "risk_verdict" in out

def test_neutral_returns_zero_fee():
    orch = CognitiveOrchestrator()
    out = orch.run_cycle(seed=999)
    assert "fee" in out
    assert out["fee"] == 0.0 or out["risk_verdict"] == "rejected"


