from pathlib import Path

p = Path("services/memory_service.py")
t = p.read_text()
t = t.replace("BeliefRepository(session).save(belief)", "BeliefRepository(session).save_snapshot(belief)")
p.write_text(t)
print("save -> save_snapshot")
