from pathlib import Path

p = Path("AI_MEMORY_SYSTEM/CURRENT_STATE.md")
t = p.read_text()

gaps = """

## Bilinen Borçlar (Known Gaps)

| # | Borç | Öncelik | Bloklayan |
|---|------|---------|-----------|
| 1 | BinderStage sadece \"wisdom\" tipini işliyor; observation/debate_result binder'dan geçmiyor | P1 | Hayır |
| 2 | ForwardOutcome pending=True set ediliyor ama finalize worker yok | P1 | Hayır |
| 3 | E2E DB persist + belief + weight update zinciri integration testi eksik | P1 | Hayır |
| 4 | Experiment Registry (Faz 159) — git_sha, risk_limits_version, feature_schema_id | P2 | Hayır |
| 5 | Replay Engine tam sürüm (Faz 162) — determinism + integrity check | P2 | #3 |

"""

# Insert before "## Mimari Notlar"
t = t.replace("## Mimari Notlar", gaps + "## Mimari Notlar")
p.write_text(t)
print("Known Gaps eklendi")
