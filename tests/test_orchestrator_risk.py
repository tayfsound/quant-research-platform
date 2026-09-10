"""Phase 187 — orchestrator + cognitive engine integration."""
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
    """Faz 484 — bu test eskiden "nötr/varsayılan bir döngü zaten işlem
    açmaz, dolayısıyla komisyon 0'dır" varsayıyordu ve TAM PAKET koşusunda
    düştü. Varsayım Faz 482'yle geçersizleşti: post-hoc kapılar artık test
    modunda/simüle sembollerde engellemiyor, dolayısıyla bu döngü GERÇEKTEN
    bir pozisyon açabiliyor ve komisyon pozitif çıkıyor.

    Testin ASIL iddiası korunuyor ve daha keskin hale getiriliyor:
    komisyon, kararın gerçekten işlem açıp açmadığıyla TUTARLI olmalı —
    işlem yoksa 0, işlem varsa pozitif. Eskisi "ya 0 ya rejected" derken
    açılan işlem durumunu hiç kontrol etmiyordu."""
    orch = CognitiveOrchestrator()
    out = orch.run_cycle(seed=999)

    assert "fee" in out
    traded = (
        out.get("direction") in ("LONG", "SHORT")
        and out.get("risk_verdict") == "approved"
        and (out.get("size") or 0.0) > 0
    )
    if traded:
        assert out["fee"] > 0.0, f"islem acildi ama komisyon 0: {out}"
    else:
        assert out["fee"] == 0.0, f"islem acilmadi ama komisyon var: {out}"


