from services.orchestrator import CognitiveOrchestrator


def test_full_cycle():
    orch = CognitiveOrchestrator()
    result = orch.run_cycle(seed=123)
    assert "direction" in result
    assert "filled_price" in result
    assert result["memory_size"] >= 0
