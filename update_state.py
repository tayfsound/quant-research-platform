from pathlib import Path

p = Path("AI_MEMORY_SYSTEM/CURRENT_STATE.md")
t = p.read_text()

old = "# Mevcut Durum -- v1.2.4 Final\n\n**Tarih:** 2026-07-31\n**Branch:** main\n**Tag:** v1.2.4\n**Test:** 234 passed"

new = "# Mevcut Durum -- v1.2.5\n\n**Tarih:** 2026-08-01\n**Branch:** main\n**Tag:** v1.2.5\n**Test:** 242 passed (240 + 2 RiskGateStage)"

t = t.replace(old, new)

# Add new completed items
addition = """
### P0 -- Risk Gate + Cleanup (2026-08-01)
- P0-17: Repo cleanup — apply_*.py, fix_*.py, *.patch, UTC silindi; .gitignore güncellendi
- P0-18: RiskGateStage eklendi (fusion sonrası size/drawdown kontrolü)
- P0-19: Tek DB persist path — _persist_and_learn sadece feedback loop
- P0-20: RiskGateStage integration test (approve + reject path'leri)

### P1 -- Fee Fix
- P1-13: Orchestrator'da pnl = outcome["pnl"] - fee (net of fee)
"""

t = t.replace("## Mimari Notlar", addition + "\n## Mimari Notlar")

# Update known gaps
old_note = "- Risk otoritesi: `GuardrailStage` (erken) + `RiskStage` (fusion sonrasi) -- ikili yapi"
new_note = "- Risk otoritesi: `GuardrailStage` (erken) + `RiskGateStage` (fusion sonrasi) -- ikili yapi ✅"

t = t.replace(old_note, new_note)

p.write_text(t)
print("CURRENT_STATE.md updated")
