import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent

# 1. Fix migration down_revision
mig = REPO / "database" / "migrations" / "versions" / "faz161_timescale_hypertable.py"
t = mig.read_text()
if "down_revision = None" in t:
    # Check if there's a previous migration
    versions = list((REPO / "database" / "migrations" / "versions").glob("*.py"))
    versions = [v for v in versions if v.name != "faz161_timescale_hypertable.py" and not v.name.startswith("__")]
    if versions:
        # Get latest revision
        latest = sorted(versions)[-1]
        rev = latest.name.split("_")[0]
        t = t.replace("down_revision = None", f'down_revision = "{rev}"')
    else:
        # First migration
        t = t.replace("down_revision = None", 'down_revision = None')
    mig.write_text(t)
    print("migration down_revision fixed")

# 2. Add Alembic upgrade to CI
ci = REPO / ".github" / "workflows" / "ci.yml"
ct = ci.read_text()
if "alembic upgrade head" not in ct:
    ct = ct.replace(
        "        run: pytest -q --ignore=tests/test_ml.py",
        "        run: |\n          alembic upgrade head\n          pytest -q --ignore=tests/test_ml.py"
    )
    ci.write_text(ct)
    print("CI + alembic upgrade head")

# 3. Test setup'ta hypertable verify
test_setup = REPO / "tests" / "conftest.py"
if test_setup.exists():
    ts = test_setup.read_text()
    if "hypertable" not in ts:
        ts += '''

def verify_hypertables():
    """Verify TimescaleDB hypertables exist."""
    from database.session_factory import SessionFactory
    import sqlalchemy as sa
    with SessionFactory.get_session() as session:
        result = session.execute(sa.text(
            "SELECT hypertable_name FROM timescaledb_information.hypertables"
        ))
        tables = {r[0] for r in result}
        assert "decisions" in tables, "decisions not hypertable"
        assert "experiment_registry" in tables, "experiment_registry not hypertable"
        assert "weight_approvals" in tables, "weight_approvals not hypertable"
'''
        test_setup.write_text(ts)
        print("conftest + hypertable verify")

# 4. Commit + push + cleanup
subprocess.run(["git", "add", "-A"], cwd=REPO, check=True)
subprocess.run(["git", "commit", "-m", "Faz 161: TimescaleDB CI integration + hypertable verify"], cwd=REPO, check=True)
subprocess.run(["git", "push", "origin", "main"], cwd=REPO, check=True)

(REPO / "faz161_ci.py").unlink()
print("[OK] Faz 161 complete")
