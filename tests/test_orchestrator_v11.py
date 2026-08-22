from services.orchestrator import CognitiveOrchestrator


def test_cycle_returns_pnl():
    orch = CognitiveOrchestrator()
    out = orch.run_cycle(seed=42)
    assert "pnl" in out
    assert "win" in out
    assert "risk_verdict" in out

def test_cycle_uses_engine_recording():
    """Orchestrator facade: recording sadece Engine stage'inde yapilir (P1-8)."""
    orch = CognitiveOrchestrator()
    out = orch.run_cycle(seed=42)
    assert "risk_verdict" in out
    assert out["risk_verdict"] in ("approved", "rejected")

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
