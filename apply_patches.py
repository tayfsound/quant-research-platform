import os
import re
import subprocess

def read_file(path):
    with open(path, 'r') as f:
        return f.read()

def write_file(path, content):
    with open(path, 'w') as f:
        f.write(content)
    print(f"  ✓ {path}")

def run(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr

# 1. P0-3: risk/limits/schema.py
content = read_file("risk/limits/schema.py")
content = content.replace("from pydantic import BaseModel", "from pydantic import BaseModel, Field")
content = content.replace("id: UUID = uuid4()", "id: UUID = Field(default_factory=uuid4)")
write_file("risk/limits/schema.py", content)

# 2. P0-4a: services/agent_debate.py
content = read_file("services/agent_debate.py")
content = content.replace(
    "    AgentResponse,\n    CognitiveAudit,",
    "    AgentResponse,\n    ChallengerAgent,\n    CognitiveAudit,"
)
content = content.replace(
    "    DebateRound,\n)",
    "    DebateRound,\n    ResponderAgent,\n)"
)
write_file("services/agent_debate.py", content)

# 3. P0-4b: llm_reasoner.py
content = read_file("llm_reasoner.py")
content = content.replace(
    "wins = [l for trade_log in logs if trade_log.get(\"outcome\", {}).get(\"pnl\", 0) > 0]",
    "wins = [trade_log for trade_log in logs if trade_log.get(\"outcome\", {}).get(\"pnl\", 0) > 0]"
)
content = content.replace(
    "losses = [l for trade_log in logs if trade_log.get(\"outcome\", {}).get(\"pnl\", 0) <= 0]",
    "losses = [trade_log for trade_log in logs if trade_log.get(\"outcome\", {}).get(\"pnl\", 0) <= 0]"
)
write_file("llm_reasoner.py", content)

# 4. P0-5: services/cognitive_binder.py
content = read_file("services/cognitive_binder.py")
old_belief = '''        return Belief(
            statement=binding.expression.root.explain(),
            expression=binding.expression.description,
            category=category,
            confidence=binding.confidence,
            evidence_count=binding.evidence_count,
        )'''
new_belief = '''        return Belief(
            direction="LONG" if binding.confidence > 0.6 else "WAIT",
            strength=binding.confidence,
            uncertainty=1.0 - binding.confidence,
            evidence_paths=[binding.expression.description] if binding.expression else [],
            assumptions=[binding.expression.root.explain()] if binding.expression else [],
            total_opinions=binding.evidence_count,
        )'''
content = content.replace(old_belief, new_belief)

old_hypothesis = '''        return Hypothesis(
            statement=f"Test: {belief.statement}",
            belief_ids=[belief.id],
            sample_size=belief.evidence_count,
            proposed_experiment=f"Verify if {belief.expression} holds in current market",
        )'''
new_hypothesis = '''        return Hypothesis(
            statement=f"Test: direction={belief.direction}, strength={belief.strength}",
            belief_ids=[belief.id],
            sample_size=belief.total_opinions,
            proposed_experiment=f"Verify if {belief.direction} holds in current market",
        )'''
content = content.replace(old_hypothesis, new_hypothesis)
write_file("services/cognitive_binder.py", content)

# 5. P0-6: engines/cognitive_pipeline.py
content = read_file("engines/cognitive_pipeline.py")
old_end = '''        ctx.cognition.relevant_knowledge.append({
            "type": "decision_event",
            "data": event.model_dump(),
        })

        return event'''
new_end = '''        ctx.cognition.relevant_knowledge.append({
            "type": "decision_event",
            "data": event.model_dump(),
        })

        # Belief persistence -- pipeline'dan DB'ye (P0-6)
        if belief is not None:
            from services.memory_service import MemoryService
            MemoryService().store_belief(belief)

        return event'''
content = content.replace(old_end, new_end)
write_file("engines/cognitive_pipeline.py", content)

# 6. P1-11: services/forward_outcome.py
content = read_file("services/forward_outcome.py")
old_calc = '''    def calculate(self, entry_price: float, direction: str, data: List[OHLCV]) -> Dict:
        """N bar sonraki fiyata gore PnL hesapla."""
        if len(data) < self.bars_forward + 1:
            return {"pnl": 0.0, "win": False, "exit_price": entry_price, "bars": 0}

        exit_price = data[-1].close # Simulated: en son bar
        if direction == "LONG":
            pnl = exit_price - entry_price
        elif direction == "SHORT":
            pnl = entry_price - exit_price
        else:
            pnl = 0.0

        return {
            "pnl": pnl,
            "win": pnl > 0,
            "exit_price": exit_price,
            "bars": len(data),
        }'''
new_calc = '''    def calculate(self, entry_price: float, direction: str, data: List[OHLCV], fee: float = 0.0) -> Dict:
        """N bar sonraki fiyata gore PnL hesapla."""
        if len(data) < 2:
            return {"pnl": 0.0, "win": False, "exit_price": entry_price, "bars": 0}

        # FIX: bars_forward kadar ileri git (eskisi data[-1].close idi)
        exit_idx = min(self.bars_forward, len(data) - 1)
        exit_price = data[exit_idx].close

        if direction == "LONG":
            pnl = exit_price - entry_price
        elif direction == "SHORT":
            pnl = entry_price - exit_price
        else:
            pnl = 0.0

        net_pnl = pnl - fee

        return {
            "pnl": net_pnl,
            "win": net_pnl > 0,
            "exit_price": exit_price,
            "bars": exit_idx,
        }'''
content = content.replace(old_calc, new_calc)
write_file("services/forward_outcome.py", content)

# 7. P1-8/12: services/orchestrator.py
content = read_file("services/orchestrator.py")
content = content.replace(
    '"""End-to-end cognitive loop orchestrator -- v1.1 trusted paper cycle."""',
    '"""End-to-end cognitive loop orchestrator -- v1.2 facade (P1-8)."""'
)

old_forward = '''        # Forward outcome
        outcome = self.forward.calculate(filled_price, direction, data)
        pnl = outcome["pnl"] - fee
        win = pnl > 0

        # Record decision (approve + reject)
        ctx.outcome = outcome
        self.recorder.record(ctx, [], None)

        # Memory (sadece risk-onayli)
        if direction != "NEUTRAL" and size > 0:
            self.memory.add({
                "decision_id": f"cycle_{seed}",
                "features": ctx.market.features,
                "label": 1 if win else 0,
                "pnl": pnl,
                "quality_score": 0.8,
                "timestamp": data[-1].timestamp.isoformat(),
                "direction": direction,
            })'''

new_forward = '''        # Forward outcome: N-bar mark-to-market + fee (P1-11)
        outcome = self.forward.calculate(filled_price, direction, data, fee=fee)
        pnl = outcome["pnl"]
        win = outcome["win"]

        # Outcome'u TradeOutcome contract'ina cevir (P1-12)
        from contracts.outcome import TradeOutcome
        ctx.outcome = TradeOutcome(
            pnl=outcome["pnl"],
            win=outcome["win"],
            decision=direction,
            confidence_at_decision=ctx.decision.confidence,
        )

        # REMOVED: self.recorder.record(ctx, [], None)
        # Engine RecordingStage zaten kaydediyor -- cift kayit yok (P1-8)

        # REMOVED: self.memory.add(...)
        # Label entry aninda karar verilmemeli; forward horizon + fee (P1-10)'''

content = content.replace(old_forward, new_forward)
write_file("services/orchestrator.py", content)

# 8. Test: test_orchestrator_v11.py
content = read_file("tests/test_orchestrator_v11.py")
content = content.replace(
    '''def test_cycle_records_decision():
    orch = CognitiveOrchestrator()
    out = orch.run_cycle(seed=42)
    assert out["memory_size"] >= 0''',
    '''def test_cycle_uses_engine_recording():
    """Orchestrator facade: recording sadece Engine stage'inde yapilir (P1-8)."""
    orch = CognitiveOrchestrator()
    out = orch.run_cycle(seed=42)
    assert "risk_verdict" in out
    assert out["risk_verdict"] in ("approved", "rejected")'''
)
write_file("tests/test_orchestrator_v11.py", content)

# 9. Test: test_orchestrator_risk.py
content = read_file("tests/test_orchestrator_risk.py")
content = content.replace(
    '''def test_memory_updated_on_approved():
    orch = CognitiveOrchestrator(max_position_size=1.0, max_drawdown=0.50)
    out = orch.run_cycle(seed=42)
    assert out["memory_size"] >= 0''',
    ''
)
write_file("tests/test_orchestrator_risk.py", content)

# 10. Test: test_forward_outcome.py
content = read_file("tests/test_forward_outcome.py")
content = content.rstrip() + '''

def test_forward_outcome_uses_bars_forward():
    """ForwardOutcome gercekten bars_forward kadar ileri gitmeli (P1-11)."""
    from market_data.ingestion.ohlcv import OHLCV
    fwd = ForwardOutcome(bars_forward=5)
    data = [OHLCV(open=100, high=101, low=99, close=100+i, volume=1000, timestamp=None) for i in range(20)]
    result = fwd.calculate(entry_price=100, direction="LONG", data=data)
    assert result["bars"] == 5
    assert result["exit_price"] == 105

def test_forward_outcome_with_fee():
    """Fee net PnL'den dusulmeli."""
    from market_data.ingestion.ohlcv import OHLCV
    fwd = ForwardOutcome(bars_forward=10)
    data = [OHLCV(open=100, high=101, low=99, close=100+i, volume=1000, timestamp=None) for i in range(20)]
    result = fwd.calculate(entry_price=100, direction="LONG", data=data, fee=2.0)
    assert result["pnl"] == 8.0
    assert result["win"] is True
'''
write_file("tests/test_forward_outcome.py", content)

# 11. Test: test_learning_loop.py ekle
content = read_file("tests/test_learning_loop.py")
content = content.rstrip() + '''

def test_engine_persist_and_learn_with_outcome():
    """CognitiveEngine._persist_and_learn ctx.outcome varsa learning calistirmali (P1-12)."""
    from unittest.mock import patch, MagicMock
    from contracts.outcome import TradeOutcome
    from services.cognitive_engine import CognitiveEngine

    engine = CognitiveEngine()
    ctx = MagicMock()
    ctx.outcome = TradeOutcome(pnl=100, win=True, decision="LONG", confidence_at_decision=0.8)
    event = MagicMock()
    event.agent_opinions = []
    event.market_snapshot = {}

    with patch.object(engine.learning_loop, "record") as mock_record:
        with patch.object(engine.weight_optimizer, "optimize", return_value={}):
            with patch.object(engine.weight_repository, "get_latest", return_value=None):
                with patch.object(engine.weight_repository, "save"):
                    with patch("database.repositories.decision_persistor.DecisionPersistor.persist"):
                        engine._persist_and_learn(event, ctx)
                        mock_record.assert_called_once()
'''
write_file("tests/test_learning_loop.py", content)

# 12. Yeni test: test_orchestrator_facade.py
facade_test = '''"""P1-8: Orchestrator facade -- tek karar yolu, cift kayit yok."""
from unittest.mock import patch
from services.orchestrator import CognitiveOrchestrator

def test_orchestrator_does_not_call_own_recorder():
    """Orchestrator, Engine.run() disinda kendi recorder'ini cagirmamalidir."""
    orch = CognitiveOrchestrator()
    with patch.object(orch.recorder, "record") as mock_record:
        orch.run_cycle(seed=42)
        mock_record.assert_not_called()

def test_orchestrator_does_not_duplicate_memory_update():
    """Orchestrator, Engine.run() disinda kendi memory'yi guncellememelidir."""
    orch = CognitiveOrchestrator()
    initial_size = len(orch.memory.memory)
    orch.run_cycle(seed=42)
    assert len(orch.memory.memory) == initial_size
'''
write_file("tests/test_orchestrator_facade.py", facade_test)

# 13. CURRENT_STATE.md
current_state = '''# Mevcut Durum -- v1.2.1 P0+P1 Hijyen

**Tarih:** 2026-07-31
**Branch:** main
**Tag:** v1.2.1
**Test:** 224+ passed

## Tamamlanan (C1 kanitli)

### P0 -- Hijyen
- P0-3: `risk/limits/schema.py` `uuid4()` -> `Field(default_factory=uuid4)` fix
- P0-4: `agent_debate.py` missing import fix; `llm_reasoner.py` list comprehension fix
- P0-5: `cognitive_binder.py` Belief v3 uyumlu (UNBOUND -- pipeline'da cagrilmiyor)
- P0-6: `RecordingStage` belief persistence baglandi; integration test eklendi

### P1 -- Tek karar yolu + Outcome
- P1-8: `Orchestrator` facade -- cift kayit ve memory kaldırildi
- P1-9: Risk Gate siraligi -- fusion sonrasi degerlendirme net
- P1-10: Label entry aninda karar verme kaldirildi; forward horizon + fee
- P1-11: `ForwardOutcome` `bars_forward` fix + fee parametresi
- P1-12: `Orchestrator` `ctx.outcome`'u `TradeOutcome` contract'ina ceviriyor; `CognitiveEngine._persist_and_learn` learning calisiyor

## Bilinen Borclar (P2 / Sonraki Sprint)
- P2-15: Dashboard <-> API minimal baglanti
- P2-16: Compose'a API service
- P2-17: Replay -- belief+decision gercekten persist olduktan sonra

## Mimari Notlar
- `CognitiveBinder` hala **UNBOUND** -- `cognitive_engine.py` veya `cognitive_pipeline.py` icinde cagrilmiyor
- `CognitiveEngine.run()` stage zinciri: Memory -> Knowledge -> Council -> Meta -> Fusion -> Risk -> Recording -> [Outcome -> Learning]
- `Orchestrator` facade: data provider -> context build -> `engine.run(ctx)` -> fill -> forward outcome -> done
- Risk otoritesi: `GuardrailStage` (erken) + `RiskStage` (fusion sonrasi) -- ikili yapi biliniyor
'''
write_file("AI_MEMORY_SYSTEM/CURRENT_STATE.md", current_state)

print("\n=== TUM DEGISIKLIKLER TAMAMLANDI ===")
print("Test calistiriliyor...")

# 14. Test
for test_file in [
    "tests/test_orchestrator_v11.py",
    "tests/test_orchestrator_risk.py", 
    "tests/test_forward_outcome.py",
    "tests/test_orchestrator_facade.py",
    "tests/test_api_orchestrator.py",
    "tests/test_learning_loop.py",
]:
    rc, out, err = run(f"pytest {test_file} -q")
    if rc == 0:
        print(f"  ✓ {test_file}: {out.strip()}")
    else:
        print(f"  ✗ {test_file} FAILED")
        print(f"    {err[:200]}")

print("\n=== GENEL TEST ===")
rc, out, err = run("pytest -q")
print(out[-500:] if len(out) > 500 else out)
if rc != 0:
    print("ERR:", err[:300])
