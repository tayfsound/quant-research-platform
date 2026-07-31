# Mevcut Durum -- v1.2.1 P0+P1 Hijyen

**Tarih:** 2026-07-31
**Branch:** main
**Tag:** v1.2.1
**Test:** 224+ passed

## Tamamlanan (C1 kanitli)

### P0 -- Hijyen
- P0-3: `risk/limits/schema.py` `uuid4()` -> `Field(default_factory=uuid4)` fix
- P0-4: `agent_debate.py` missing import fix; `llm_reasoner.py` list comprehension fix
- P0-5: `cognitive_binder.py` Belief v3 uyumlu (UNBOUND -- pipeline'da cagrilmiyor)
- P0-6: `RecordingStage` belief persistence baglandi; integration test eklendi

### P1 -- Tek karar yolu + Outcome
- P1-8: `Orchestrator` facade -- cift kayit ve memory kaldırildi
- P1-9: Risk Gate siraligi -- fusion sonrasi degerlendirme net
- P1-10: Label entry aninda karar verme kaldirildi; forward horizon + fee
- P1-11: `ForwardOutcome` `bars_forward` fix + fee parametresi
- P1-12: `Orchestrator` `ctx.outcome`'u `TradeOutcome` contract'ina ceviriyor; `CognitiveEngine._persist_and_learn` learning calisiyor

## Bilinen Borclar (P2 / Sonraki Sprint)
- P2-15: Dashboard <-> API minimal baglanti
- P2-16: Compose'a API service
- P2-17: Replay -- belief+decision gercekten persist olduktan sonra

## Mimari Notlar
- `CognitiveBinder` hala **UNBOUND** -- `cognitive_engine.py` veya `cognitive_pipeline.py` icinde cagrilmiyor
- `CognitiveEngine.run()` stage zinciri: Memory -> Knowledge -> Council -> Meta -> Fusion -> Risk -> Recording -> [Outcome -> Learning]
- `Orchestrator` facade: data provider -> context build -> `engine.run(ctx)` -> fill -> forward outcome -> done
- Risk otoritesi: `GuardrailStage` (erken) + `RiskStage` (fusion sonrasi) -- ikili yapi biliniyor
