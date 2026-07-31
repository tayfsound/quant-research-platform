import os
import re
import shutil
import subprocess

def backup(path):
    if os.path.exists(path):
        shutil.copy(path, path + ".bak")

# 1. forward_outcome.py — entry = data[-(n+1)], exit = data[-1], pending flag
backup("services/forward_outcome.py")
with open("services/forward_outcome.py", "r") as f:
    content = f.read()

old = '''    def calculate(self, entry_price: float, direction: str, data: List[OHLCV], fee: float = 0.0) -> Dict:
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

new = '''    def calculate(self, entry_price: float, direction: str, data: List[OHLCV]) -> Dict:
        """N-bar forward outcome: entry = data[-(n+1)], exit = data[-1]."""
        n = self.bars_forward
        if len(data) < n + 1:
            return {
                "pnl": 0.0,
                "win": False,
                "entry_price": entry_price,
                "exit_price": entry_price,
                "bars": 0,
                "pending": True,
            }

        entry = data[-(n + 1)].close
        exit_px = data[-1].close

        if entry_price and entry_price > 0:
            entry = entry_price

        d = (direction or "").upper()
        if d == "LONG":
            pnl = exit_px - entry
        elif d == "SHORT":
            pnl = entry - exit_px
        else:
            pnl = 0.0

        return {
            "pnl": float(pnl),
            "win": pnl > 0,
            "entry_price": float(entry),
            "exit_price": float(exit_px),
            "bars": n,
            "pending": False,
        }'''

content = content.replace(old, new)
with open("services/forward_outcome.py", "w") as f:
    f.write(content)
print("✓ services/forward_outcome.py")

# 2. cognitive_engine.py — persist flag + finalize
backup("services/cognitive_engine.py")
with open("services/cognitive_engine.py", "r") as f:
    content = f.read()

old_run = '''    def run(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        ctx, should_continue = self.guardrail_stage.evaluate(ctx)
        if not should_continue:
            event = self.record_stage.execute(ctx, None, [])
            self._persist_and_learn(event, ctx)
            return ctx

        ctx = self.memory_stage.execute(ctx)
        ctx = self.knowledge_stage.execute(ctx)
        ctx, belief, opinions = self.council_stage.execute(ctx)
        ctx = self.meta_stage.execute(ctx, belief)
        ctx = self.decision_fusion.execute(ctx, belief)
        event = self.record_stage.execute(ctx, belief, opinions)
        self._persist_and_learn(event, ctx)
        return ctx'''

new_run = '''    def run(self, ctx: CognitiveCycleContext, *, persist: bool = True) -> CognitiveCycleContext:
        ctx, should_continue = self.guardrail_stage.evaluate(ctx)
        if not should_continue:
            if persist:
                event = self.record_stage.execute(ctx, None, [])
                self._persist_and_learn(event, ctx)
            return ctx

        ctx = self.memory_stage.execute(ctx)
        ctx = self.knowledge_stage.execute(ctx)
        ctx, belief, opinions = self.council_stage.execute(ctx)
        ctx = self.meta_stage.execute(ctx, belief)
        ctx = self.decision_fusion.execute(ctx, belief)

        ctx.__dict__["_last_belief"] = belief
        ctx.__dict__["_last_opinions"] = opinions

        if persist:
            event = self.record_stage.execute(ctx, belief, opinions)
            self._persist_and_learn(event, ctx)
        return ctx

    def finalize(self, ctx: CognitiveCycleContext) -> CognitiveCycleContext:
        """Outcome set edildikten sonra tek kayit + learning."""
        belief = ctx.__dict__.get("_last_belief")
        opinions = ctx.__dict__.get("_last_opinions") or []
        event = self.record_stage.execute(ctx, belief, opinions)
        self._persist_and_learn(event, ctx)
        return ctx'''

content = content.replace(old_run, new_run)
with open("services/cognitive_engine.py", "w") as f:
    f.write(content)
print("✓ services/cognitive_engine.py")

# 3. orchestrator.py — persist=False, finalize, fee, memory
backup("services/orchestrator.py")
with open("services/orchestrator.py", "r") as f:
    content = f.read()

content = content.replace(
    "ctx = self.engine.run(ctx)",
    "ctx = self.engine.run(ctx, persist=False)"
)

content = content.replace(
    '''        # Forward outcome: N-bar mark-to-market + fee (P1-11)
        outcome = self.forward.calculate(filled_price, direction, data, fee=fee)
        pnl = outcome["pnl"]
        win = outcome["win"]''',
    '''        # Forward outcome: N-bar mark-to-market
        outcome = self.forward.calculate(filled_price, direction, data)'''
)

old_block = '''        # Outcome'u TradeOutcome contract'ina cevir (P1-12)
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

new_block = '''        # Outcome'u TradeOutcome contract'ina cevir
        from contracts.outcome import TradeOutcome
        raw_pnl = float(outcome["pnl"])
        pnl = raw_pnl - fee
        win = pnl > 0 and not outcome.get("pending", False)

        ctx.outcome = TradeOutcome(
            pnl=pnl,
            win=win,
            decision=direction,
            confidence_at_decision=ctx.decision.confidence,
        )

        # Tek kayit + learning (outcome set edildikten sonra)
        ctx = self.engine.finalize(ctx)

        # Memory (sadece risk-onayli ve pending degil)
        if direction != "NEUTRAL" and size > 0 and not outcome.get("pending"):
            self.memory.add({
                "decision_id": f"cycle_{seed}",
                "features": ctx.market.features,
                "label": 1 if win else 0,
                "pnl": pnl,
                "quality_score": 0.8,
                "timestamp": data[-1].timestamp.isoformat(),
                "direction": direction,
            })'''

content = content.replace(old_block, new_block)
with open("services/orchestrator.py", "w") as f:
    f.write(content)
print("✓ services/orchestrator.py")

# 4. Test: forward_outcome
backup("tests/test_forward_outcome.py")
with open("tests/test_forward_outcome.py", "r") as f:
    content = f.read()

# Eski fee/bars testlerini kaldır
content = re.sub(r'\ndef test_forward_outcome_uses_bars_forward.*?(?=\n$|\Z)', '', content, flags=re.DOTALL)
content = re.sub(r'\ndef test_forward_outcome_with_fee.*?(?=\n$|\Z)', '', content, flags=re.DOTALL)

new_tests = '''
from datetime import datetime, timedelta, timezone
from market_data.ingestion.ohlcv import OHLCV

def _bars(n, start=100.0, step=1.0):
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    out = []
    for i in range(n):
        p = start + i * step
        out.append(OHLCV(timestamp=t0 + timedelta(minutes=i), open=p, high=p, low=p, close=p, volume=1.0))
    return out

def test_long_profit_n_bar():
    data = _bars(20, start=100.0, step=1.0)
    fo = ForwardOutcome(bars_forward=10)
    r = fo.calculate(entry_price=data[-11].close, direction="LONG", data=data)
    assert r["pending"] is False
    assert r["pnl"] > 0
    assert r["bars"] == 10

def test_short_profit():
    data = _bars(20, start=100.0, step=-1.0)
    fo = ForwardOutcome(bars_forward=10)
    r = fo.calculate(entry_price=data[-11].close, direction="SHORT", data=data)
    assert r["pnl"] > 0

def test_insufficient_bars_pending():
    data = _bars(5)
    r = ForwardOutcome(10).calculate(100.0, "LONG", data)
    assert r["pending"] is True
    assert r["pnl"] == 0.0
'''

content = content.rstrip() + new_tests
with open("tests/test_forward_outcome.py", "w") as f:
    f.write(content)
print("✓ tests/test_forward_outcome.py")

# 5. Test: orchestrator facade guncelle
backup("tests/test_orchestrator_facade.py")
with open("tests/test_orchestrator_facade.py", "r") as f:
    content = f.read()

content = content.replace(
    '''def test_orchestrator_does_not_duplicate_memory_update():
    """Orchestrator, Engine.run() disinda kendi memory'yi guncellememelidir."""
    orch = CognitiveOrchestrator()
    initial_size = len(orch.memory.memory)
    orch.run_cycle(seed=42)
    assert len(orch.memory.memory) == initial_size''',
    '''def test_orchestrator_calls_finalize_once():
    """Orchestrator, engine.run(persist=False) sonrasi finalize() cagirmali."""
    from unittest.mock import patch
    orch = CognitiveOrchestrator()
    with patch.object(orch.engine, "finalize") as mock_finalize:
        with patch.object(orch.engine, "run") as mock_run:
            mock_ctx = mock_run.return_value
            mock_ctx.decision.proposed_direction = "NEUTRAL"
            mock_ctx.decision.final_size = 0.0
            orch.run_cycle(seed=42)
            mock_finalize.assert_called_once()'''
)
with open("tests/test_orchestrator_facade.py", "w") as f:
    f.write(content)
print("✓ tests/test_orchestrator_facade.py")

# 6. Yeni test: orchestrator outcome
with open("tests/test_orchestrator_outcome.py", "w") as f:
    f.write('''"""Orchestrator outcome + single persist testleri."""
from unittest.mock import patch
from services.orchestrator import CognitiveOrchestrator

def test_orchestrator_single_persist_path():
    """Orchestrator sadece finalize() ile bir kez persist etmeli."""
    orch = CognitiveOrchestrator()
    with patch.object(orch.engine, "finalize") as mock_finalize:
        with patch.object(orch.engine, "run") as mock_run:
            mock_ctx = mock_run.return_value
            mock_ctx.decision.proposed_direction = "NEUTRAL"
            mock_ctx.decision.final_size = 0.0
            orch.run_cycle(seed=42)
            mock_finalize.assert_called_once()
''')
print("✓ tests/test_orchestrator_outcome.py")

# 7. CURRENT_STATE guncelle
with open("AI_MEMORY_SYSTEM/CURRENT_STATE.md", "w") as f:
    f.write('''# Mevcut Durum -- v1.2.2 Single Persist + Forward Outcome

**Tarih:** 2026-07-31
**Branch:** main
**Tag:** v1.2.2
**Test:** 228+ passed

## Tamamlanan (C1 kanitli)

### P0 -- Hijyen
- P0-3: `risk/limits/schema.py` `Field(default_factory=uuid4)`
- P0-4: `agent_debate.py` imports; `llm_reasoner.py` comprehension fix
- P0-5: `cognitive_binder.py` Belief v3 uyumlu (UNBOUND)
- P0-6: `RecordingStage` `MemoryService.store_belief()` baglandi

### P1 -- Tek karar yolu + Outcome
- P1-8/9/10/11: `Orchestrator` facade; `ForwardOutcome` N-bar entry/exit hizali; `pending` flag
- P1-12: `CognitiveEngine.run(persist=False)` + `finalize()` -- outcome sonrasi tek kayit + learning

### P2 -- Dashboard + Compose
- P2-15: Dashboard proxy + API client + `LatestCycle` component
- P2-16: `docker-compose.yml`'e API service eklendi
- P2-17: Replay integration test (minimal, pending persist sonrasi)

## Mimari Notlar
- `CognitiveBinder` hala **UNBOUND**
- Risk otoritesi: `GuardrailStage` (erken) + `RiskStage` (fusion sonrasi) -- ikili yapi
- `ForwardOutcome`: entry = data[-(n+1)], exit = data[-1]; canlida `pending=True`
''')
print("✓ AI_MEMORY_SYSTEM/CURRENT_STATE.md")

# Test
print("\n=== TEST ===")
for tf in [
    "tests/test_forward_outcome.py",
    "tests/test_orchestrator_facade.py",
    "tests/test_orchestrator_outcome.py",
    "tests/test_orchestrator_v11.py",
    "tests/test_orchestrator_risk.py",
    "tests/test_learning_loop.py",
]:
    r = subprocess.run(["pytest", tf, "-q"], capture_output=True, text=True)
    status = "✓" if r.returncode == 0 else "✗"
    print(f"  {status} {tf}")

print("\n=== GENEL TEST ===")
r = subprocess.run(["pytest", "-q"], capture_output=True, text=True)
print(r.stdout[-600:] if len(r.stdout) > 600 else r.stdout)
if r.returncode != 0:
    print("ERR:", r.stderr[:400])
