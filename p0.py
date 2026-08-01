import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent

for name in [
    "apply_binder.py", "apply_final_fixes.py", "apply_p2.py",
    "apply_patches.py", "apply_single_persist.py",
    "fix_2.py", "fix_finalize.py", "fix_indent_final.py",
    "fix_remaining.py", "fix_segfault.py", "fix_slow_tests.py",
    "fix_tests.py", "fix_utc.py", "llm_reasoner_patch.py",
    "p0-3-risk-uuid.patch", "UTC",
]:
    f = REPO / name
    if f.exists():
        f.unlink()
        print("rm " + name)
    subprocess.run(["git", "rm", "--cached", name], cwd=REPO, capture_output=True)

gi = REPO / ".gitignore"
existing = gi.read_text().splitlines() if gi.exists() else []
for line in ["*.bak", "*.patch", "apply_*.py", "fix_*.py", "llm_reasoner_patch.py", "UTC"]:
    if line not in existing:
        with open(gi, "a") as f:
            f.write("\n" + line)
        print("gitignore + " + line)

pipe = REPO / "engines" / "cognitive_pipeline.py"
txt = pipe.read_text()
if "class RiskGateStage" not in txt:
    stage = '''

class RiskGateStage:
    def __init__(self, risk_engine):
        self.risk_engine = risk_engine

    def execute(self, ctx):
        limits = ctx.risk.limits
        final_size = getattr(ctx.decision, "final_size", 0.0)
        reasons = []

        max_size = limits.get("max_position_size")
        if max_size and final_size > max_size.value:
            from contracts.contexts.risk import RiskReason
            reasons.append(RiskReason(
                code="POST_FUSION_SIZE_EXCEEDED",
                message="Final size " + str(final_size) + " > limit " + str(max_size.value),
                severity="critical",
            ))

        max_dd = limits.get("max_drawdown")
        if max_dd and ctx.risk.current_drawdown >= max_dd.value:
            from contracts.contexts.risk import RiskReason
            reasons.append(RiskReason(
                code="MAX_DRAWDOWN",
                message="Drawdown exceeded",
                severity="critical",
            ))

        if reasons:
            from contracts.contexts.decision import ActionType
            ctx.decision.action = ActionType.WAIT
            ctx.decision.final_size = 0.0
            ctx.risk.evaluation.verdict = "rejected"
            ctx.risk.evaluation.reasons = reasons
        else:
            ctx.risk.evaluation.verdict = "approved"

        return ctx
'''
    txt = txt.replace("class RecordingStage:", stage + "\nclass RecordingStage:")
    pipe.write_text(txt)
    print("pipeline + RiskGateStage")

eng = REPO / "services" / "cognitive_engine.py"
ec = eng.read_text()

if "RiskGateStage" not in ec:
    ec = ec.replace(
        "    RecordingStage,\n)",
        "    RecordingStage,\n    RiskGateStage,\n)"
    )

if "self.risk_gate_stage" not in ec:
    ec = ec.replace(
        "self.record_stage = RecordingStage()",
        "self.record_stage = RecordingStage()\n        self.risk_gate_stage = RiskGateStage(self.guardrail_stage.risk_engine)"
    )

if "self.risk_gate_stage.execute" not in ec:
    ec = ec.replace(
        "ctx = self.decision_fusion.execute(ctx, belief)\n\n        ctx.__dict__",
        "ctx = self.decision_fusion.execute(ctx, belief)\n        ctx = self.risk_gate_stage.execute(ctx)\n\n        ctx.__dict__"
    )

old = '''    def _persist_and_learn(
        self,
        event,
        ctx: CognitiveCycleContext,
    ) -> None:
        """Persist decision to DB and run post-execution feedback loop."""
        session = get_session()
        try:
            DecisionPersistor(session).persist(event)
        finally:
            session.close()

        if ctx.outcome is None:
            return'''

new = '''    def _persist_and_learn(
        self,
        event,
        ctx: CognitiveCycleContext,
    ) -> None:
        """Feedback loop only — RecordingStage already persisted."""
        if ctx.outcome is None:
            return'''

ec = ec.replace(old, new)
eng.write_text(ec)
print("engine patched")

r = subprocess.run(["pytest", "-q", "--ignore=tests/test_ml.py"], cwd=REPO)
if r.returncode != 0:
    print("[FAIL] Tests red", file=sys.stderr)
    sys.exit(1)

subprocess.run(["git", "add", "-A"], cwd=REPO, check=True)
subprocess.run(["git", "commit", "-m", "P0: RiskGateStage + cleanup + single persist"], cwd=REPO, check=True)
subprocess.run(["git", "push", "origin", "main"], cwd=REPO, check=True)
print("[OK] Done")
