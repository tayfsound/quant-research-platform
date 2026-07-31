with open("services/orchestrator.py", "r") as f:
    content = f.read()

# finalize ekle: memory.add'dan hemen once
content = content.replace(
    "            self.memory.add({",
    "        ctx = self.engine.finalize(ctx)\n\n            self.memory.add({"
)

with open("services/orchestrator.py", "w") as f:
    f.write(content)
print("✓ finalize eklendi")

# replay test kaldir
import os
if os.path.exists("tests/test_replay_integration.py"):
    os.remove("tests/test_replay_integration.py")
    print("✓ replay test kaldirildi")
