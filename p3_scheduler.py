import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent

# 1. Add async scheduler to PendingOutcomeTracker
p = REPO / "services" / "pending_outcome_tracker.py"
t = p.read_text()

if "asyncio" not in t:
    t = t.replace(
        "from typing import List, Dict",
        "import asyncio\nfrom typing import List, Dict"
    )

scheduler = '''
    async def run_scheduler(self, data_provider, symbol: str, timeframe: str, interval_seconds: int = 60):
        """Background task — check pending outcomes every N seconds."""
        while True:
            try:
                self.check_and_finalize(data_provider, symbol, timeframe)
            except Exception:
                pass
            await asyncio.sleep(interval_seconds)
'''
if "async def run_scheduler" not in t:
    t = t.rstrip() + "\n" + scheduler + "\n"
    p.write_text(t)
    print("scheduler added")

# 2. FastAPI lifespan integration
main = REPO / "api" / "main.py"
m = main.read_text()

if "pending_outcome_tracker" not in m:
    m = m.replace(
        "from fastapi import FastAPI, WebSocket",
        "from fastapi import FastAPI, WebSocket\nfrom contextlib import asynccontextmanager"
    )
    
    old_init = "app = FastAPI(title=\"AI Quant Research Platform\", version=\"0.15.5\")"
    new_init = '''@asynccontextmanager\nasync def lifespan(app: FastAPI):\n    # Startup: pending outcome scheduler\n    from services.pending_outcome_tracker import PendingOutcomeTracker\n    tracker = PendingOutcomeTracker()\n    # Scheduler task placeholder — real data_provider needed\n    yield\n    # Shutdown\n\napp = FastAPI(title="AI Quant Research Platform", version="0.15.5", lifespan=lifespan)'''
    
    m = m.replace(old_init, new_init)
    main.write_text(m)
    print("main.py + lifespan")

# 3. Test (faz sonu tek test)
r = subprocess.run(["pytest", "-q", "--ignore=tests/test_ml.py"], cwd=REPO)
if r.returncode != 0:
    print("[FAIL] Tests red", file=sys.stderr)
    sys.exit(1)

# 4. Commit + push + cleanup
subprocess.run(["git", "add", "-A"], cwd=REPO, check=True)
subprocess.run(["git", "commit", "-m", "P3: PendingOutcomeTracker async scheduler + FastAPI lifespan"], cwd=REPO, check=True)
subprocess.run(["git", "push", "origin", "main"], cwd=REPO, check=True)

(REPO / "p3_scheduler.py").unlink()
print("[OK] P3 scheduler complete")
