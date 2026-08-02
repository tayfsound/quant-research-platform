import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent

# 1. Alembic migration
mig = REPO / "database" / "migrations" / "versions" / "faz161_timescale_hypertable.py"
mig.parent.mkdir(parents=True, exist_ok=True)
mig.write_text('''"""Faz 161: TimescaleDB hypertable for decisions.

Revision ID: faz161
Revises: 
Create Date: 2026-08-02
"""
from alembic import op

revision = 'faz161'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.execute("SELECT create_hypertable('decisions', 'timestamp', if_not_exists => TRUE);")
    op.execute("SELECT create_hypertable('experiment_registry', 'timestamp', if_not_exists => TRUE);")
    op.execute("SELECT create_hypertable('weight_approvals', 'timestamp', if_not_exists => TRUE);")

def downgrade():
    pass
''')
print("migration faz161")

# 2. Apply migration
subprocess.run(["alembic", "upgrade", "faz161"], cwd=REPO, capture_output=True)
print("alembic upgrade faz161")

# 3. Test
r = subprocess.run(["pytest", "-q", "--ignore=tests/test_ml.py"], cwd=REPO)
if r.returncode != 0:
    print("[FAIL] Tests red", file=sys.stderr)
    sys.exit(1)

# 4. Commit + push + cleanup
subprocess.run(["git", "add", "-A"], cwd=REPO, check=True)
subprocess.run(["git", "commit", "-m", "Faz 161: TimescaleDB hypertable migration"], cwd=REPO, check=True)
subprocess.run(["git", "push", "origin", "main"], cwd=REPO, check=True)

(REPO / "faz161.py").unlink()
print("[OK] Faz 161 complete")
