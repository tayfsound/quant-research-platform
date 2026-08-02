# Mevcut Durum -- v1.2.5

**Tarih:** 2026-08-01
**Branch:** main
**Tag:** v1.2.5
**Test:** 255 passed (240 + 2 RiskGateStage)

## Tamamlanan (C1 kanitli)

### P0 -- Hijyen
- P0-3: `risk/limits/schema.py` `Field(default_factory=uuid4)`
- P0-4: `agent_debate.py` imports; `llm_reasoner.py` comprehension fix
- P0-5: `cognitive_binder.py` Belief v3 uyumlu
- P0-6: `RecordingStage` `MemoryService.store_belief()` baglandi

### P1 -- Tek karar yolu + Outcome
- P1-8/9/10/11: `Orchestrator` facade; `ForwardOutcome` N-bar entry/exit hizali; `pending` flag
- P1-12: `CognitiveEngine.run(persist=False)` + `finalize()` -- outcome sonrasi tek kayit + learning

### P2 -- Dashboard + Compose
- P2-15: Dashboard proxy + API client + `LatestCycle` component
- P2-16: `docker-compose.yml`'e API service eklendi

### Binder + Learning
- `BinderStage` eklendi; `CognitiveEngine` stage zincirinde Knowledge -> Binder -> Council
- `CognitiveBinder` **BOUND**
- `WeightOptimizer` Pydantic AgentOpinion uyumlu
- `llm_reasoner.py` httpx tabanli HTTP client (subprocess kaldirildi)


### P0 -- Risk Gate + Cleanup (2026-08-01)
- P0-17: Repo cleanup — apply_*.py, fix_*.py, *.patch, UTC silindi; .gitignore güncellendi
- P0-18: RiskGateStage eklendi (fusion sonrası size/drawdown kontrolü)
- P0-19: Tek DB persist path — _persist_and_learn sadece feedback loop
- P0-20: RiskGateStage integration test (approve + reject path'leri)

### P1 -- Fee Fix
- P1-13: Orchestrator'da pnl = outcome["pnl"] - fee (net of fee)

### P1 -- E2E Integration Tests
- P1-17: E2E persist chain — DB + belief + weight learning (mock assert)

### P2 -- Experiment Registry Temeli (Faz 159)
- P2-21: ExperimentRegistry contract (git_sha, risk_limits_version, feature_schema_id, prompt_hash, model_id)
- P2-22: ExperimentRegistryRepository (save, get_by_git_sha)
- P2-23: experiment_repository type hints fix (from __future__ import annotations)



## Bilinen Borçlar (Known Gaps)

    • WeightApproval API endpoint'leri (/weights/pending, /approve, /reject) | P3 | Yeni

| # | Borç | Öncelik | Bloklayan |
|---|------|---------|-----------|
| 1 | BinderStage sadece "wisdom" tipini işliyor; observation/debate_result binder'dan geçmiyor | P1 | Hayır |
| 2 | ForwardOutcome pending=True set ediliyor ama finalize worker yok | P1 | Hayır |
| 3 | E2E DB persist + belief + weight update zinciri integration testi eksik | P1 | Hayır |
| 4 | Experiment Registry (Faz 159) — git_sha, risk_limits_version, feature_schema_id | P2 | Hayır |
| 5 | Replay Engine tam sürüm (Faz 162) — determinism + integrity check | P2 | #3 |

## Mimari Notlar
- Risk otoritesi: `GuardrailStage` (erken) + `RiskGateStage` (fusion sonrasi) -- ikili yapi ✅
- `ForwardOutcome`: entry = data[-(n+1)], exit = data[-1]; canlida `pending=True`
- Learning: `finalize()` outcome set edildikten sonra `_persist_and_learn` calisir
