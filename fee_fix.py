from pathlib import Path
p = Path("services/orchestrator.py")
t = p.read_text()
t = t.replace('pnl = outcome["pnl"]', 'pnl = outcome["pnl"] - fee')
p.write_text(t)
print("fee fix")
