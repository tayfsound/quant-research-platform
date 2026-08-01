from pathlib import Path

p = Path("AI_MEMORY_SYSTEM/CURRENT_STATE.md")
t = p.read_text()

# Update test count
t = t.replace("**Test:** 245 passed", "**Test:** 246 passed")

# Mark closed gaps
t = t.replace(
    "    • E2E DB persist + belief + weight update zinciri integration testi eksik | P1 | Hayır",
    "    • ✅ E2E DB persist + belief + weight update zinciri integration testi | P1 | Tamam"
)

# Add new completed items
old = "### P2 -- Experiment Registry Temeli (Faz 159)"
new = """### P1 -- E2E Integration Tests
- P1-17: E2E persist chain — DB + belief + weight learning (mock assert)

### P2 -- Experiment Registry Temeli (Faz 159)"""

t = t.replace(old, new)

p.write_text(t)
print("CURRENT_STATE.md final update")
