from pathlib import Path

p = Path("AI_MEMORY_SYSTEM/CURRENT_STATE.md")
t = p.read_text()

old = "    • BinderStage sadece \"wisdom\" tipini işliyor; observation/debate_result binder'dan geçmiyor | P1 | Hayır"
new = "    • BinderStage sadece \"wisdom\" tipini işliyor (by design) — observation/debate_result doğrudan knowledge olarak kullanılır | P1 | Hayır"

t = t.replace(old, new)
p.write_text(t)
print("BinderStage scope documented")
