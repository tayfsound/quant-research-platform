from pathlib import Path

p = Path("AI_MEMORY_SYSTEM/CURRENT_STATE.md")
t = p.read_text()

t = t.replace("**Test:** 246 passed", "**Test:** 248 passed")

old = "    • ForwardOutcome pending=True ama finalize worker yok | P1 | Hayır"
new = "    • ✅ PendingOutcomeTracker skeleton (mock data finalize) | P2 | Tamam"

t = t.replace(old, new)

p.write_text(t)
print("CURRENT_STATE.md final")
