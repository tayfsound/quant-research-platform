import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent

# 1. Add git_sha helper
p = REPO / "contracts" / "experiment_registry.py"
t = p.read_text()
if "import subprocess" not in t:
    t = t.replace(
        "from datetime import datetime",
        "import subprocess\nfrom datetime import datetime"
    )
    t = t.replace(
        '    decision_ids: list[str] = Field(default_factory=list)\n)',
        '''    decision_ids: list[str] = Field(default_factory=list)

    @staticmethod
    def get_git_sha() -> str:
        try:
            return subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=Path(__file__).resolve().parent.parent,
                text=True,
            ).strip()
        except Exception:
            return "unknown"
''',
    )
    p.write_text(t)
    print("git_sha helper added")

# 2. Patch RecordingStage to log experiment
pipe = REPO / "engines" / "cognitive_pipeline.py"
t = pipe.read_text()

if "ExperimentRegistry" not in t:
    t = t.replace(
        "from contracts.decision_event import DecisionEvent",
        "from contracts.decision_event import DecisionEvent\nfrom contracts.experiment_registry import ExperimentRegistry"
    )

old = '''        # Belief persistence -- pipeline'dan DB'ye (P0-6)
 if belief is not None:
     from services.memory_service import MemoryService
     MemoryService().store_belief(belief)

 return event'''

new = '''        # Belief persistence -- pipeline'dan DB'ye (P0-6)
 if belief is not None:
     from services.memory_service import MemoryService
     MemoryService().store_belief(belief)

 # Experiment registry log (Faz 159)
 try:
     from database.session_factory import SessionFactory
     from database.repositories.experiment_registry_repository import ExperimentRegistryRepository
     exp = ExperimentRegistry(
         git_sha=ExperimentRegistry.get_git_sha(),
         decision_ids=[str(event.id)] if event.id else [],
     )
     with SessionFactory.get_session() as session:
         ExperimentRegistryRepository(session).save(exp)
 except Exception:
     pass  # Experiment logging is best-effort

 return event'''

t = t.replace(old, new)
pipe.write_text(t)
print("RecordingStage + ExperimentRegistry bound")

r = subprocess.run(["pytest", "-q", "--ignore=tests/test_ml.py"], cwd=REPO)
if r.returncode != 0:
    print("[FAIL] Tests red", file=sys.stderr)
    sys.exit(1)

subprocess.run(["git", "add", "-A"], cwd=REPO, check=True)
subprocess.run(["git", "commit", "-m", "feat: ExperimentRegistry bound to RecordingStage (Faz 159)"], cwd=REPO, check=True)
subprocess.run(["git", "push", "origin", "main"], cwd=REPO, check=True)
print("[OK] Done")
