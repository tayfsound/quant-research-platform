import re

# 1. Fix ForwardOutcome
with open("services/forward_outcome.py", "r") as f:
    content = f.read()

# Eski calculate fonksiyonunu bul ve değiştir
old_pattern = r'def calculate\(self, entry_price: float, direction: str, data: List\[OHLCV\]\) -> Dict:.*?(?=\n    def |\Z)'
new_func = '''def calculate(self, entry_price: float, direction: str, data: List[OHLCV], fee: float = 0.0) -> Dict:
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

content = re.sub(old_pattern, new_func, content, flags=re.DOTALL)
with open("services/forward_outcome.py", "w") as f:
    f.write(content)
print("✓ services/forward_outcome.py fixed")

# 2. Fix Orchestrator — recorder.record() ve memory.add() kaldır
with open("services/orchestrator.py", "r") as f:
    content = f.read()

# recorder.record() çağrısını kaldır
content = re.sub(
    r'\n\s*# Record decision \(approve \+ reject\)\n\s*ctx\.outcome = outcome\n\s*self\.recorder\.record\(ctx, \[\], None\)\n',
    '\n        # Outcome\'u TradeOutcome contract\'ina cevir (P1-12)\n        from contracts.outcome import TradeOutcome\n        ctx.outcome = TradeOutcome(\n            pnl=outcome["pnl"],\n            win=outcome["win"],\n            decision=direction,\n            confidence_at_decision=ctx.decision.confidence,\n        )\n\n        # REMOVED: self.recorder.record(ctx, [], None)\n        # Engine RecordingStage zaten kaydediyor -- cift kayit yok (P1-8)\n',
    content
)

# memory.add() bloğunu kaldır
content = re.sub(
    r'\n\s*# Memory \(sadece risk-onayli\)\n\s*if direction != "NEUTRAL" and size > 0:\n\s*self\.memory\.add\(\{[^}]*\}\)\n',
    '\n        # REMOVED: self.memory.add(...)\n        # Label entry aninda karar verilmemeli; forward horizon + fee (P1-10)\n',
    content
)

# forward outcome çağrısını fee ile güncelle
content = content.replace(
    'outcome = self.forward.calculate(filled_price, direction, data)',
    'outcome = self.forward.calculate(filled_price, direction, data, fee=fee)'
)
content = content.replace(
    'pnl = outcome["pnl"] - fee\n        win = pnl > 0',
    'pnl = outcome["pnl"]\n        win = outcome["win"]'
)

with open("services/orchestrator.py", "w") as f:
    f.write(content)
print("✓ services/orchestrator.py fixed")

# 3. Fix test — event.confidence set et
with open("tests/test_learning_loop.py", "r") as f:
    content = f.read()

content = content.replace(
    '    event = MagicMock()\n    event.agent_opinions = []\n    event.market_snapshot = {}',
    '    event = MagicMock()\n    event.confidence = 0.8\n    event.final_action = "ENTER_LONG"\n    event.agent_opinions = []\n    event.market_snapshot = {}'
)

with open("tests/test_learning_loop.py", "w") as f:
    f.write(content)
print("✓ tests/test_learning_loop.py fixed")

print("\n=== TEST ===")
import subprocess
result = subprocess.run(["pytest", "tests/test_forward_outcome.py", "tests/test_learning_loop.py", "tests/test_orchestrator_facade.py", "-v", "--tb=short"], capture_output=True, text=True)
print(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
if result.returncode != 0:
    print("STDERR:", result.stderr[:500])
