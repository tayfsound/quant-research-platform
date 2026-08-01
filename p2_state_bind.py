from pathlib import Path

p = Path("AI_MEMORY_SYSTEM/CURRENT_STATE.md")
t = p.read_text()

# Mark ExperimentRegistry binding
old = "    • Experiment Registry — decision_ids bağlama, git_sha otomatik çekme | P2 | Hayır"
new = "    • ✅ ExperimentRegistry bound to RecordingStage (git_sha + decision_ids auto-log) | P2 | Tamam"

t = t.replace(old, new)

# Update test count
t = t.replace("**Test:** 246 passed", "**Test:** 246 passed")

p.write_text(t)
print("CURRENT_STATE.md updated")
