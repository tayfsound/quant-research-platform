from pathlib import Path

p = Path("AI_MEMORY_SYSTEM/CURRENT_STATE.md")
t = p.read_text()

# Add ExperimentRegistry to completed
old = "### P1 -- Fee Fix\n- P1-13: Orchestrator'da pnl = outcome[\"pnl\"] - fee (net of fee)"
new = """### P1 -- Fee Fix
- P1-13: Orchestrator'da pnl = outcome["pnl"] - fee (net of fee)

### P2 -- Experiment Registry Temeli (Faz 159)
- P2-21: ExperimentRegistry contract (git_sha, risk_limits_version, feature_schema_id, prompt_hash, model_id)
- P2-22: ExperimentRegistryRepository (save, get_by_git_sha)
- P2-23: experiment_repository type hints fix (from __future__ import annotations)"""

t = t.replace(old, new)

# Update test count
t = t.replace("**Test:** 242 passed", "**Test:** 245 passed")

p.write_text(t)
print("CURRENT_STATE.md updated")
