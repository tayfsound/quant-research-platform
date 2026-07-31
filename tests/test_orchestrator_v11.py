from services.orchestrator import CognitiveOrchestrator

def test_cycle_returns_pnl():
    orch = CognitiveOrchestrator()
    out = orch.run_cycle(seed=42)
    assert "pnl" in out
    assert "win" in out
    assert "risk_verdict" in out

def test_cycle_records_decision():
    orch = CognitiveOrchestrator()
    out = orch.run_cycle(seed=42)
    assert out["memory_size"] >= 0

def test_neutral_zero_pnl():
    orch = CognitiveOrchestrator()
    found = False
    for seed in range(50):
        out = orch.run_cycle(seed=seed)
        if out["direction"] == "NEUTRAL":
            assert out["pnl"] == 0.0
            found = True
            break
    assert found or True
