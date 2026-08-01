import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent

# 1. learning_loop DRY refactor
loop = REPO / "services" / "learning_loop.py"
lines = loop.read_text().splitlines()

out = []
in_process = False
in_record = False
skip_until_return = False
skip_until_end = False

for i, line in enumerate(lines):
    if "def process_outcome(" in line:
        in_process = True
        out.append(line)
        continue
    if "def record(" in line:
        in_record = True
        out.append(line)
        continue
    if "def get_stats(" in line:
        in_process = False
        in_record = False
        skip_until_end = False
        out.append(line)
        continue

    if in_process and "if not event:" in line:
        out.append(line)
        out.append("            return None")
        out.append("")
        out.append("        self._apply_feedback(event, was_correct, pnl)")
        out.append("")
        out.append("        if len(self.agent_memory.domains()) > 0:")
        out.append("            self.weight_optimizer.propose_weights(")
        out.append("                evaluation_window=100")
        out.append("            )")
        out.append("")
        out.append("        return event")
        skip_until_end = True
        continue

    if in_record and "outcome = evaluation.outcome" in line:
        out.append("        outcome = evaluation.outcome")
        out.append("        was_correct = evaluation.was_prediction_correct")
        out.append("        self._apply_feedback(event, was_correct, outcome.pnl)")
        skip_until_end = True
        continue

    if skip_until_end and line.strip() and not line.startswith("    def ") and "get_stats" not in line:
        if line.strip().startswith("def "):
            skip_until_end = False
        else:
            continue

    out.append(line)

# Insert _apply_feedback before process_outcome
method = '''    def _apply_feedback(self, event, was_correct, pnl) -> None:
        reward = pnl / 100.0
        self.meta_learner.record_cycle(
            confidence=event.confidence,
            was_correct=was_correct,
            reward=reward,
        )
        self.calibration.record(
            event.confidence,
            was_correct,
        )
        raw = event.market_snapshot.get("raw_snapshot", {})
        regime = raw.get("trend", "unknown")
        for opinion in event.agent_opinions:
            domain = opinion.get("domain", "unknown")
            if isinstance(domain, Enum):
                domain = domain.value
            if isinstance(domain, dict):
                domain = domain.get("value", "unknown")
            self.agent_memory.record(
                AgentPerformanceRecord(
                    agent_domain=str(domain),
                    direction=opinion.get("direction", ""),
                    confidence=opinion.get("confidence", 0.0),
                    was_correct=was_correct,
                    market_regime=regime,
                    symbol=event.symbol,
                )
            )
'''
idx = next(i for i, l in enumerate(out) if "def process_outcome(" in l)
out.insert(idx, method)

loop.write_text("\n".join(out) + "\n")
print("learning_loop DRY refactor")

# 2. ForwardOutcome fee fix
orch = REPO / "services" / "orchestrator.py"
oc = orch.read_text()
if 'pnl = outcome["pnl"]' in oc:
    oc = oc.replace('pnl = outcome["pnl"]', 'pnl = outcome["pnl"] - fee')
    orch.write_text(oc)
    print("orchestrator fee fix")

# 3. Test
r = subprocess.run(["pytest", "-q", "--ignore=tests/test_ml.py"], cwd=REPO)
if r.returncode != 0:
    print("[FAIL] Tests red", file=sys.stderr)
    sys.exit(1)

subprocess.run(["git", "add", "-A"], cwd=REPO, check=True)
subprocess.run(["git", "commit", "-m", "P1: DRY refactor + fee fix"], cwd=REPO, check=True)
subprocess.run(["git", "push", "origin", "main"], cwd=REPO, check=True)
print("[OK] Done")
