# Mevcut Durum -- v1.4.0 (Backtest bloğu + Portfolio Engine bloğu tamam)

**Tarih:** 2026-08-04
**Branch:** main
**Son commit (HEAD):** 056f7f8 Sprint 6 (backtest persist+dashboard) + bu oturumun devamı (Faz 171 Portfolio Engine)
**Test:** 308 passed, 1 xfailed (TimescaleDB hypertable, local'de non-empty table nedeniyle — bkz. borç #6), 1 skipped

**Önemli not:** Bu dosya, Faz 161-167 commit'lerinden sonra güncellenmemiş kalmıştı (dokümantasyon
sürüklenmesi — roadmap'te 5 kez tekrarlanan risk, burada gerçekleşti). Aşağıdaki liste 2026-08-04
tarihinde koda karşı yeniden doğrulandı.

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



### Faz 159-167 (commit'lerde var, bu dosyada eksikti — şimdi eklendi)
- Faz 159: ExperimentRegistry contract + RecordingStage.execute'e bağlandı (git_sha, risk_limits_version, ...)
- Faz 160: Meta Optimizer approval gate (human-in-the-loop) — WeightApproval pending/approve/reject
- Faz 161: TimescaleDB migration dosyası + CI hypertable verify testi (local'de xfail, bkz. borç #6)
- Faz 162: ReplayEngine deterministic replay + verify_integrity (hash) + Replay API router
- Faz 163: ForwardOutcome fee-aware (gross/net pnl) + PendingOutcomeTracker → WeightOptimizer learning trigger
- Faz 164: ReplayEngine determinism testi (gerçek DB persist → replay) + Dashboard PendingApprovals/ExperimentList
- Faz 165: **Meta Optimizer Auto-Approval** (bu oturumda gerçek entegrasyon tamamlandı — bkz. aşağı)
- Faz 166: ReplayEngine E2E DB assert testi
- Faz 167: WeightApproval approve → weight snapshot C1 testi

### Faz 165 — Auto-Approval (2026-08-04, bu oturumda tamamlandı)
Önceki oturumdan kalan durum: `api/rest/weights.py` içinde `/weights/auto-reject` ve `/weights/metrics`
endpoint'leri zaten vardı ama çağırdıkları `WeightApprovalRepository.auto_reject_stale()` ve
`.approval_latency_metrics()` metodları **yoktu** — klasik ada (island) hatası, endpoint çağrılsa
`AttributeError` ile patlardı. `tests/test_faz165_auto_approval.py` de bu nedenle kırmızıydı.
Ayrıca `services/weight_optimizer.py` içinde bozuk bir `try:` indent hatası vardı — 19 test dosyası
collection aşamasında crash ediyordu (suit hiç çalışmıyordu).

Yapılanlar (C1 kanıtlı):
- `services/weight_optimizer.py`: indent hatası düzeltildi (satır 140-141)
- `contracts/weight_approval.py`: `expires_at`, `decided_at` alanları eklendi (önceden sessizce drop ediliyordu — Pydantic v2 default `extra=ignore`)
- `database/repositories/weight_approval_repository.py`: `WeightApprovalModel`'e `expires_at`/`decided_at` kolonları, `auto_reject_stale()` ve `approval_latency_metrics()` gerçek implementasyon (raw SQL değil, ORM + Python p95 — Postgres-specific `PERCENTILE_CONT` kaldırıldı, SQLite/test uyumlu)
- `database/migrations/versions/faz165_weight_approval_ttl.py`: gerçek Alembic migration, local DB'ye uygulandı (`alembic upgrade faz165` çalıştırıldı, kolonlar doğrulandı)
- `api/rest/weights.py`: duplicate import düzeltildi, `reject()` artık `decided_at` set ediyor
- `tests/test_faz165_auto_approval.py`: yanlış alan adı (`created_at` — modelde yok, gerçek alan `timestamp`) düzeltildi; latency testi gerçek approved kayıttan hesaplanan değeri assert ediyor (sadece key varlığı değil)
- Kanıt: `pytest -q` → 265 passed (önceki: 2 failed + 19 collection error)

### Ek bulgular — kod incelemesi sırasında (2026-08-04)
- `contracts/experiment_registry.py`: `get_git_sha()` `pathlib.Path` kullanıyordu ama import etmiyordu;
  `except Exception` bunu yutup sessizce `"unknown"` döndürüyordu. `engines/cognitive_pipeline.py:225`
  (RecordingStage, gerçek pipeline yolu) bunu çağırıyor — yani her deneyde `git_sha` hep `"unknown"`
  kaydediliyordu, Faz 159'un asıl amacı (deneyleri git commit'e pinlemek) fiilen çalışmıyordu. Import
  eklendi, doğrulandı: `ExperimentRegistry.get_git_sha()` artık gerçek SHA döndürüyor.
- `tests/test_weight_approval_e2e.py`: dosya adı/docstring "approve endpoint applies weights" diyordu
  ama gerçek test body'si `WeightApprovalRepository`'i tamamen mockluyor ve sadece `GET /pending`'i
  çağırıyordu — `/approve` endpoint'ine hiç dokunmuyordu. Gerçek DB + gerçek `POST /approve` + gerçek
  `WeightRepository.get_latest()` assert eden bir E2E testle değiştirildi.

### Repo hijyeni
- Root'ta kalan tek-seferlik "patcher script"ler (`pay_debt.py`, `update_state.py`,
  `faz163_forward_outcome_worker.py`, `faz164_replay_determinism.py`, `faz165_auto_approval.py`) ve
  `.fix_backups/` silindi. Bunlar önceki oturumdan kalan, kaynağı string-replace ile patch'leyen
  yardımcı scriptlerdi; faz163/164'ün patch'leri gerçek kaynağa (services/, contracts/) zaten
  uygulanmıştı ve doğrulandı, faz165'inki ise yarım kalmıştı (yukarıda anlatıldığı gibi elle
  tamamlandı). Script'lerin kendisi uygulama kodu değil; repo kökünde bırakılmaları yanlışlıkla
  tekrar çalıştırılıp kaynağı bozma riski taşıyordu (weight_optimizer.py indent hatası muhtemelen
  böyle oluştu).

## Bilinen Borçlar (Known Gaps)

| # | Borç | Öncelik | Bloklayan |
|---|------|---------|-----------|
| 3 | E2E DB persist + belief + weight update zinciri integration testi eksik | ~~P1~~ **Kapandı** | tests/test_e2e_scenarios.py — guardrail-red/outcome-none/outcome-var, üçü de gerçek DB'ye karşı yeşil (2026-08-04) |
| 8 | `engines/memory_engine.py` (`MemoryEngine.record_cycle` → `MemoryConsolidator.capture_cycle`) `CognitiveEngine.run()`/`finalize()` içinde hiçbir yerden çağrılmıyor — gerçek ada. `capture_cycle`, `relevant_knowledge` içindeki `type="observation"` öğelerini `semantic.consolidated_beliefs`'e taşıyor ama şu an pipeline'da hiçbir stage `"observation"` tipi üretmiyor, yani şu anda zararsız ama tamamen kopuk. | P2 | Hayır |
| 6 | Alembic history'de 2 head var: `faz165` (0005 zincirinden) ve `faz161` (f8fa21f0e94a zincirinden, hiç merge edilmedi). `faz161`'in `create_hypertable()` çağrıları local DB'de `decisions`/`experiment_registry`/`weight_approvals` tabloları dolu olduğu için başarısız oluyor (`migrate_data=>true` gerekiyor — Timescale, boş olmayan tabloyu varsayılan olarak hypertable'a çevirmiyor). Bu bir alan/version eksikliği değil, gerçek veri var. CI'da DB boş başladığı için sorun yok. Local'de düzeltmek için: ya `migrate_data=>true` ile devam et (veri kaybı yok ama chunk'lara bölünür), ya da local DB'yi sıfırdan kurup migration zincirini baştan çalıştır. | P2 | Migration testi (roadmap Faz 182 gate) |
| 7 | `weight_approvals` tablosunun kendisi migration zincirinde hiçbir yerde `CREATE TABLE` ile oluşturulmuyor (muhtemelen geçmişte `Base.metadata.create_all()` ile elle kuruldu). Sıfırdan bir DB'de `alembic upgrade head` bu tabloyu oluşturmaz. | P1 | Migration testi (roadmap Faz 182 gate) |
| 9 | ~~İkinci, kopuk Replay motoru~~ **Kapandı (2026-08-04):** Proje sahibi kararı: `services/replay/` gerçek motor, `services/replay_engine.py` bunun üstünde ince facade. Yapılanlar: (1) `engines/replay/replay_engine.py`'deki `DeterministicReplayEngine` düzeltildi — eskiden `decision_engine.evaluate()` snapshot'ı hiç kullanmıyordu ve verification'ı orijinal event'e karşı (yani kendi kendine, tautolojik — hep True) yapıyordu; şimdi `evaluate(snapshot)` restore edilmiş state'i kullanıyor ve replay edilmiş sonucu orijinalin hash'ine karşı doğruluyor (bkz. yeni test: `test_replay_engine_flags_divergence_when_replay_differs`, replay farklı sonuç üretirse `verified=False` gerçekten yakalanıyor). (2) `services/replay_engine.py.replay_decision()` artık `build_snapshot()` + `ReplayVerifier` + `ReplaySeedManager` kullanıyor (eski ad-hoc `hashlib`+global `random.seed()` yerine); dönüş sözlüğüne gerçek `verification` alanı eklendi. (3) `verify_integrity()` — eskiden var olmayan bir `integrity_hash` DB kolonuna karşı kıyaslıyordu, yani her zaman `False` dönen ölü kod idi; artık `replay_decision()`'ı çağırıp gerçek hash doğrulamasını delegize ediyor. (4) Yan bulgu: real-DB replay path'inde `ctx.decision.proposed_direction` restore edilirken sadece `proposed_direction` anahtarına bakıyordu ama gerçek DB satırında bu alan `direction` — yani gerçek kayıtlarda yön hiç restore edilmiyordu (sadece mock'lu testler çalışıyordu); `direction` fallback eklendi. Kanıt: `tests/test_faz164_replay_determinism.py::test_persist_then_replay` artık `result["verification"]["verified"] is True`'yu gerçek DB'ye karşı assert ediyor. `pytest -q`: 269 passed. | ~~P1~~ **Kapandı** | — |
| 10 | **`api/rest/replay.py` iki endpoint'i de (`/sessions`, `/{session_id}`) hiç çalışmıyordu** — `ReplayEngine()` repo'suz (`belief_repo=None, decision_repo=None`) instantiate ediliyordu, her çağrı `{"error": "repositories_not_configured"}` dönüyordu. `SessionFactory` ile gerçek `BeliefRepository`/`DecisionPersistor` enjekte edildi; yeni `POST /replay/decision/{id}` endpoint'i eklendi (tek karar için gerçek hash-doğrulamalı replay). Kanıt: `tests/test_replay_decision_api.py` — gerçek DB'ye kaydedilmiş bir karar, gerçek HTTP çağrısıyla replay edilip `verification.verified=True` dönüyor. | ~~P1~~ **Kapandı** | — |
| 11 | `database/repositories/decision_persistor.py` (production'ın gerçekten kullandığı, `DecisionRecorder` üzerinden) `market_snapshot`'ı `agent_contributions`'a hiç yazmıyordu — `services/decision_persistor.py` (sadece testlerin kullandığı, farklı bir kopya) yazıyordu. Sonuç: gerçek kaydedilmiş kararlarda replay'in snapshot restore'u hep boş dönüyordu. `market_snapshot` append'i eklendi, doğrulandı (`snapshot_restored: True`). **Kapatılmadı, ayrı borç olarak kaldı (#12): iki ayrı `DecisionPersistor` sınıfı var, tek kaynağa indirilmedi** — bu proje sahibinin kararını gerektiren bir "iki beyin" durumu, replay motoru kararına benzer. | ~~P1~~ (snapshot fix) **Kapandı** | — |
| 12 | **İki ayrı `DecisionPersistor` sınıfı var:** `database/repositories/decision_persistor.py` (gerçek üretim yolu — `DecisionRecorder` bunu kullanıyor, `list_recent`/`get_by_symbol`/`outcome` kolonu/`ON CONFLICT DO NOTHING` var) ve `services/decision_persistor.py` (sadece testlerin ve eski replay kodunun kullandığı, `list_recent` yok, `outcome` yazmıyor). API artık production'ın kullandığı (`database/repositories/...`) sınıfa bağlandı (replay, deneyler). Hangi sınıfın kalacağına — ya da `services/decision_persistor.py`'ın tamamen kaldırılıp testlerin de `database/repositories/...`'a taşınmasına — karar verilmedi. | P1 | Proje sahibi kararı |
| 13 | **`experiment_registry` tablosu hiçbir migration'da `CREATE TABLE` ile oluşturulmuyordu — Faz 159'dan beri her `ExperimentRegistryRepository.save()` çağrısı `RecordingStage.execute()`'daki çıplak `except Exception: pass` içinde sessizce patlıyordu.** Yani "ExperimentRegistry bound to RecordingStage" iddiası hiçbir zaman gerçek bir DB satırı üretmemişti. `faz166_experiment_registry_table.py` migration'ı eklendi ve uygulandı; `GET /api/v1/experiments/` de aslında `{"experiments": []}` döndüren bir placeholder'dı (`repo.get_by_git_sha("")` çağırıp sonucu atıyordu) — `ExperimentRegistryRepository.list_recent()` eklendi, endpoint gerçek veriyi dönüyor artık. Kanıt: `tests/test_experiment_registry_real_persist.py` — gerçek bir cognitive cycle çalıştırılıp API'den gerçek (non-"unknown") git_sha ile geri geldiği doğrulanıyor. | ~~P0~~ **Kapandı** | — |
| 14 | **Sprint 2 dashboard gate kapandı (2026-08-04):** `LatestCycle`, `PendingApprovals`, `ExperimentList` bileşenleri Faz 164'te yazılmış ama `App.tsx`'e hiç import edilmemiş/render edilmemişti — NavBar'da sekmeleri bile yoktu, tarayıcıdan asla erişilemiyorlardı. Üçü de artık `App.tsx`/`NavBar.tsx`'e bağlı (`cycle`/`approvals`/`experiments` sekmeleri). Yeni `ReplayView.tsx` eklendi (`POST /replay/decision/{id}` tetikler, `verification.verified`'ı gösterir) — roadmap'in "tarayıcıdan replay tetiklenip aynı sonucu üretebiliyor mu" gate'i buna karşılık geliyor. Doğrulama: `vite dev` sunucusu ayağa kalktı, `App.tsx`'in transpile edilmiş halinde `ReplayView` gerçekten yükleniyor (curl ile doğrulandı); gerçek bir tarayıcıda tıklama testi yapılmadı (bu ortamda tarayıcı yok) ama backend endpoint'i ayrıca gerçek DB'ye karşı test edildi (`test_replay_decision_api.py`). **Önceden var olan, ilgisiz bir sorun:** `npm run build` (`tsc -b`) `AIReasoning.tsx` ve `LivePredictions.tsx`'te bu oturumdan önce var olan tip hatalarıyla başarısız oluyor (muhtemelen tipsiz `useState()` → `never[]` çıkarımı); bu dosyalara dokunulmadı, kapsam dışı bırakıldı. | P2 (build hatası) | Hayır (dev server çalışıyor) |
| 15 | **🔴 `ctx.risk.limits`'i üretimde hiçbir kod yolu doldurmuyor.** `POST /cognitive/run` (`api/rest/cognitive.py`) boş bir context ile `engine.run()` çağırıyor; `RiskEngine.execute()` her zaman `MISSING_LIMIT` ile reddediyor. **CognitiveEngine tabanlı üretim yolu şu an asla gerçek bir işlem onaylamıyor.** Ayrıca üç ayrı, birbiriyle uyumsuz "risk limit" temsili var (`risk/limits/schema.py` pydantic `RiskLimit` — `.verify()` yok; `risk/limits/enforcement.py` `RiskEnforcer`/`RiskLimit` dataclass — ayrı arayüz; `RiskEngine.execute()`'ın gerçekte beklediği `.value`+`.verify(secret)->bool` arayüzü — hiçbir yerde gerçek implement edilmemiş, sadece testlerde `FakeLimit` olarak mock'lanmış). Üçünü tek bir gerçek implementasyona indirip `/cognitive/run`'a bağlamak gerekiyor — bu proje sahibinin önceliklendirme kararını gerektirir (hangi tasarım kalacak, imzalı/hash'li mi olacak). | **P0** | Gerçek bir kararın üretimde onaylanabilmesi |
| 16 | `services/embedding_service.py` (`SentenceTransformer`) hiçbir testte çalıştırılmamış — sadece `ctx.market.features` doluyken tetiklenen yoldan geçiyor, ve standart `transformers.AutoModel/AutoTokenizer` mock deseninde gerçek bir `TypeError` ile patlıyor (`self.to(device)`, sentence-transformers kendi cihaz tespitini mock'lanmış modelle bozuyor). Gerçek bir backtest/production akışının feature vermesi gerekeceği an bu test-altyapısı sorunu da çözülmeli. | P2 | Backtest'e gerçek feature girişi |

### Sprint 3 (Faz 167 bloğu) — Vektörize backtest çekirdeği (2026-08-04)
Önceki durumda `backtest/` klasörü zaten vardı ama roadmap'in istediği şey değildi:
`WalkForwardEngine` tek bir `List[float]` fiyat serisi + `strategy(train) -> int`
callable'ı üzerinde çalışıyordu (çok-sembol matris işlemi yok), embargo/gap
kavramı yoktu (train ile test bitişik — leakage riski). Onu yerinde bozmadım
(mevcut `tests/test_backtest.py` hâlâ ona bağlı), yanına gerçek olanı ekledim:

- `backtest/vectorized_engine.py` — `VectorizedBacktestEngine`: `{symbol: [OHLCV,...]}`
  + `signals[n_symbols, n_bars]` alıp tamamen numpy matris işlemleriyle (bar
  başına Python döngüsü yok) pnl/fee/equity curve hesaplıyor. Test:
  `test_vectorized_engine_handles_full_symbol_time_matrix_at_once` — 50 sembol
  × 5000 bar'lık gerçekçi bir matrisi hızlıca işliyor.
- `backtest/embargo_walk_forward.py` — `EmbargoWalkForwardSplitter`: train/test
  arasına zorunlu `embargo` bar'lık bir boşluk koyan index splitter (lookback
  pencereli feature'ların sızıntısını önlemek için). `embargo=0` eski
  bitişik davranışla geriye dönük uyumlu.
- Doğruluk kanıtı: `tests/test_vectorized_backtest.py` — elle hesaplanmış 2
  sembollü bir örnek üzerinde pnl/fee/equity curve tam olarak doğrulanıyor
  (D1 barı: "bilinen bir sentetik equity curve'de doğru sonucu üretiyor mu");
  embargo gap'in gerçekten uygulandığı, train/test index'lerinin hiç
  kesişmediği, geçersiz parametrelerin reddedildiği ayrı testlerle kanıtlı.
- `pyproject.toml`'a `numpy` eklendi — zaten kurulu/kullanılıyordu (muhtemelen
  transformers/sklearn'den geliyordu) ama hiç deklare edilmemişti; artık
  doğrudan import ettiğim için deklare ettim.
- **Bilinçli olarak yapılmadı:** CognitiveEngine entegrasyonu (roadmap bunu
  Sprint 5'e koyuyor — "Replay ↔ Backtest entegrasyonu", aynı `CognitiveEngine.run()`
  çağrısının farklı ölçekte kullanıldığını doğrulama). Bugünkü motor bağımsız,
  strateji-agnostik bir çekirdek; henüz gerçek karar mantığına bağlanmadı.
- **Kalan Sprint 5-6 işi:** Sprint 5 (Replay↔Backtest, aynı CognitiveEngine.run()
  paylaşımı + determinism audit), Sprint 6 (`backtest_runs` tablosu + persist
  + dashboard bağlantısı) henüz başlanmadı.

### Sprint 4 (Faz 167 bloğu) — Metrik motoru (2026-08-04)
`analytics/metrics/engine.py` (`MetricsEngine`) ve `analytics/metrics/equity.py`
(`EquityAnalytics`) zaten vardı — Sharpe, Sortino, Max Drawdown, Calmar, VaR95,
Win Rate, Profit Factor tanımlıydı — ama **hiçbir yerden çağrılmıyordu ve tek
bir testi yoktu**, bir başka saf ada. Roadmap'in istediği listeye göre:

- Eksik metrikler eklendi: `expectancy()`, `recovery_factor()`, `ulcer_index()`,
  `mar_ratio()` (roadmap MAR'ı Calmar'dan ayrı bir kalem olarak listeliyor;
  bu motor rolling-window ayrımı yapmadığı için ikisi aynı formülü kullanıyor —
  yorum satırında dürüstçe belirtildi).
- **Gerçek bug bulundu ve düzeltildi:** `calmar_ratio`'nun CAGR hesabı üs olarak
  `1/len(equity)` kullanıyordu — bu her bar'ı bir YIL gibi ele alır, günlük/saatlik
  bar'larda CAGR'ı ciddi şekilde yanlış hesaplar (sessizce). `periods_per_year`
  parametresi eklendi (varsayılan 252); regresyon testi eski formülle yeniyi
  karşılaştırıp gerçekten farklı sonuç ürettiğini kanıtlıyor.
- Kanıt: `tests/test_metrics_engine.py` — her metrik, temiz sayılar üreten
  elle seçilmiş bir `equity=[100,200,100,400]` eğrisi üzerinde elle hesaplanmış
  referans değerle karşılaştırılıyor (D1 barı). Ayrıca Sprint 3'ün
  `VectorizedBacktestEngine.equity_curve` çıktısının doğrudan bu metriklere
  beslenebildiğini kanıtlayan bir entegrasyon testi eklendi — ikisi ayrı ada
  olarak kalmasın diye.
- `pytest -q`: 295 passed.

### Sprint 5 (Faz 167 bloğu) — Replay ↔ Backtest entegrasyonu + determinizm denetimi (2026-08-04)
- `backtest/cognitive_backtest_runner.py` eklendi: her bar/sembol için
  **gerçek `CognitiveEngine.run()`**'u çağırıyor (replay'in tek-karar için
  kullandığı aynı fonksiyon) ve sonucu Sprint 3'ün `VectorizedBacktestEngine`'ine
  besliyor — ayrı, basitleştirilmiş bir "backtest karar mantığı" YAZILMADI
  (bu tam olarak CognitiveEngine/Orchestrator "iki beyin" sorununu bir kat
  aşağıda tekrar üretirdi). Kanıt: `test_backtest_runner_actually_invokes_cognitive_engine_run`
  — `engine.run`'a `wraps=` ile spy koyup gerçekten 10 kez (2 sembol × 5 bar)
  çağrıldığını doğruluyor.
- **Determinizm denetimi — gerçek bug bulundu ve düzeltildi:** `CouncilOrchestrator.deliberate()`
  ağırlıkları uygulamak için her zaman `WeightRepository.get_latest()` çağırıyordu.
  Bir backtest geçmişteki bir bar'ı simüle ederken bu, o an sistemin GERÇEKTEN
  o tarihte sahip olduğu ağırlıkları değil, **şu anki en güncel (gelecekte
  öğrenilmiş) ağırlıkları** kullanır — klasik look-ahead sızıntısı, roadmap'in
  bu konuşmada "defalarca vurgulanan nokta" dediği tam olarak bu. Düzeltme:
  `WeightRepository.get_by_id()` eklendi; `CouncilOrchestrator`/`CouncilStage`/
  `CognitiveEngine`'e `pinned_weight_snapshot_id` parametresi eklendi (varsayılan
  `None` = eski davranış, canlı sistemde hiçbir şey değişmedi). Kanıt:
  `test_backtest_is_deterministic_with_a_pinned_weight_snapshot` — aynı pin
  edilmiş snapshot ile iki ayrı backtest çalıştırması birebir aynı sonucu
  üretiyor.
- `datetime.now()` denetimi: `engines/cognitive_pipeline.py`, `services/cognitive_engine.py`,
  `services/guardrail_stage.py`, `engines/risk_engine.py`, `services/agent_memory.py`,
  `services/weight_optimizer.py` tarandı — karar YOLUNDA tek `datetime.now()`
  kullanımı `weight_optimizer.py`'de bir approval TTL'i (insan onay son kullanma
  tarihi) için, kararın kendisini etkilemiyor; determinizm riski değil.
- **Yeni, önemli bulgu (P0):** `ctx.risk.limits`'i gerçek üretimde **hiçbir kod
  yolu** doldurmuyor — `api/rest/cognitive.py`'deki `POST /cognitive/run`
  bomboş bir `CognitiveCycleContext()` oluşturup direkt `engine.run()` çağırıyor.
  Sonuç: `RiskEngine.execute()` her zaman `MISSING_LIMIT` ile reddediyor —
  **CognitiveEngine yolu üretimde şu an asla gerçek bir kararı onaylamıyor.**
  Ayrıca üç farklı, birbirinden habersiz "risk limit" temsili var:
  `risk/limits/schema.py` (`RiskLimit` pydantic, `.verify()` yok),
  `risk/limits/enforcement.py` (`RiskEnforcer`/`RiskLimit` dataclass, ayrı arayüz),
  ve `RiskEngine.execute()`'ın gerçekte beklediği arayüz (`.value` + `.verify(secret)->bool`)
  — bu üçüncüsü hiçbir yerde gerçek olarak implement edilmemiş, sadece test
  dosyalarında `FakeLimit` adıyla mock'lanmış. `backtest/cognitive_backtest_runner.py`
  bunun için kendi minimal `_UnlimitedPositionLimit`'ini kullanıyor (dördüncü
  bir temsil eklemek yerine, gerçek arayüzü taklit ediyor ve bunu docstring'de
  açıkça belirtiyor). **Bu üç risk-limit tasarımını tek bir gerçek implementasyona
  indirmek ve `/cognitive/run`'a bağlamak ayrı, öncelikli bir karar/iş gerektiriyor.**
- **Yeni bulgu (P2, kapsam dışı bırakıldı):** `services/embedding_service.py`
  (`SentenceTransformer`) hiçbir testte hiç çalıştırılmamış — sadece
  `ctx.market.features` doluyken tetiklenen `DecisionContextBuilder.enrich()`
  → `SemanticSearch.find_similar_episodes()` yolundan geçiyor, ve mevcut
  standart `transformers.AutoModel/AutoTokenizer` mock deseni altında
  `self.to(device)` çağrısında gerçek bir `TypeError` ile patlıyor
  (`sentence_transformers` kendi cihaz tespitini yapıyor, mock'lanmış model
  bunu bozuyor). Backtest runner bilinçli olarak `ctx.market.features`
  set etmiyor (diğer tüm geçen full-cycle testler de aynı şekilde bu yoldan
  kaçınıyor) — gerçek bir backtest'in feature'ları karar motoruna vermesi
  gerekecek, o zaman bu test-altyapısı sorunu da çözülmeli.
- `pytest -q`: 298 passed.

### Sprint 6 (Faz 167 bloğu) — Persist + dashboard bağlantısı (2026-08-04) — **Backtest bloğu tamam**
- `contracts/backtest_run.py` (`BacktestRun`) + `database/migrations/versions/faz167_backtest_runs_table.py`
  ile gerçek `backtest_runs` tablosu (Class 2 — silme/update metodu yok,
  sadece `save`/`get_by_id`/`list_recent`). Migration local DB'ye uygulandı
  ve doğrulandı.
- `backtest/backtest_orchestrator.py` — `run_and_persist_backtest()`: Sprint
  5'in `run_cognitive_backtest()`'ini çalıştırır, Sprint 4'ün `MetricsEngine`'i
  ile TÜM metrik setini (sharpe/sortino/calmar/mar/ulcer/recovery/win_rate/
  profit_factor/expectancy) hesaplar, `experiment_registry`'nin `get_git_sha()`'ı
  ile git_sha'yı damgalar, sonucu DB'ye yazar. `inf`/`nan` değerler JSON/Postgres
  `json` kolonunu bozmasın diye `None`'a sanitize ediliyor (profit_factor/
  recovery_factor drawdown yokken `inf` dönebiliyor — bu gerçek bir edge case,
  test bunu tetikledi).
- `api/rest/backtest.py`: `POST /backtest/run` (deterministik `MockOHLCVAdapter`
  ile — gerçek borsa geçmiş veri ingestion'ı henüz yok, bu roadmap'in kendi
  sıralamasında Execution Layer/market_data genişletmesinden sonraki bir iş)
  ve `GET /backtest/runs`. `api/main.py`'a router eklendi.
- `dashboard/src/views/BacktestRuns.tsx`: "Run Backtest" butonu + son
  koşuların listesi (PnL, Sharpe, Max DD) — `App.tsx`/`NavBar.tsx`'e bağlandı.
- **Gate kanıtı** (roadmap: "Bir backtest çalıştırıp, sonucun deterministik
  olarak tekrarlanabildiğini ve tüm metriklerin doğru hesaplandığını
  kanıtlayan entegrasyon testi"): `tests/test_backtest_persistence.py` —
  (1) gerçek bir koşu DB'ye yazılıyor, `max_drawdown`'ın DB'den okunan
  equity curve'den bağımsız olarak yeniden hesaplanabildiği kanıtlanıyor;
  (2) aynı pinlenmiş weight snapshot ile iki ayrı, iki ayrı DB satırına
  yazılan koşu birebir aynı metrikleri/equity curve'ü üretiyor.
- `pytest -q`: 300 passed. Backend uçtan uca doğrulandı (gerçek HTTP çağrısı,
  `/backtest/run` → gerçek DB satırı → `/backtest/runs`'ta görünüyor);
  dashboard tarafı `vite dev` ile transpile doğrulaması yapıldı (gerçek
  tarayıcı bu ortamda yok, bkz. Sprint 2'nin aynı notu).
- **Faz 167 bloğu (roadmap Sprint 3-6) böylece tamamlandı.**

## Faz 171 — Portfolio Engine (2026-08-04, aynı oturum)

### Sprint 7 — Çoklu varlık veri modeli
`OHLCV`/`OHLCVProvider` zaten varlık-sınıfından bağımsızdı (crypto'ya özgü
alan yok) — roadmap'in "mevcut mimari zaten asset-independent tasarlanmıştı"
iddiası doğrulandı. Eksik olan, portföy riskinin gruplayabileceği bir
varlık-sınıfı etiketiydi:
- `market_data/asset_class.py`: `AssetClass` enum (crypto/equity_index/
  commodity/fx/bond) + `SYMBOL_ASSET_CLASS` statik eşleme.
- `market_data/multi_asset_dataset.py`: `generate_multi_asset_dataset()` —
  her sembol için ayrı seed'li deterministik `MockOHLCVAdapter`, aynı
  `{symbol: [OHLCV,...]}` şeklini kullanıyor (backtest/cognitive_backtest_runner.py
  ve risk/limits/portfolio.py ile doğrudan uyumlu, yeni bir paralel veri
  formatı yok).
- Gerçek borsa üzerinden çapraz-varlık veri ingestion'ı (equity/commodity/fx/bond
  için gerçek bir sağlayıcı) henüz yok — sadece crypto için `BinanceProvider`
  var. Bu ayrı, büyük bir iş (roadmap'te de zaten Execution Layer/exchange
  entegrasyonundan bağımsız bir görev).

### Sprint 8 — Portföy-bazlı risk motoru
- `risk/limits/portfolio.py`: `PortfolioRiskEngine` — kovaryans matrisi
  (`np.cov`, population/bias=True, projenin diğer istatistiklerinin
  kullandığı population-std konvansiyonuyla tutarlı), parametrik portföy VaR
  (`z * sqrt(w^T Σ w) * portfolio_value`), `check_portfolio_var_limit()`.
  **`risk/limits/`'in bir uzantısı** — tekil sembol otoritesi
  (`RiskEngine`/`RiskGateStage`) değişmedi, bu sadece onların göremediği
  çapraz-sembol katmanını ekliyor.
- Kanıt: `tests/test_portfolio_risk_engine.py` — elle seçilmiş, temiz sayılar
  üreten iki getiri serisi (`B = 2×A`, mükemmel korelasyon) üzerinde kovaryans
  matrisi VE portföy VaR'ı ($4935, z=1.645) elle hesaplanmış referansla
  birebir doğrulanıyor; korelasyonlu iki pozisyonun aynı notional'da
  korelasyonsuz olandan gerçekten daha yüksek VaR ürettiği ayrıca kanıtlanıyor
  (bu "korelasyon-ayarlı" olmanın tam kendisi).

### Sprint 9 — Portföy-seviyesi Decision Fusion
- `services/portfolio_fusion.py`: `PortfolioFusionStage.fuse()` — tekil
  sembol kararlarından (zaten `CognitiveEngine.run()` ile üretilmiş) gelen
  önerilen pozisyon boyutlarını alır, `PortfolioRiskEngine` ile portföy VaR'ı
  kontrol eder; limit aşılırsa TÜM pozisyonları aynı oranda ölçekleyip VaR'ı
  tam olarak limite çeker (limiti gevşetmiyor/bypass etmiyor — tek-sembol
  `RiskGateStage` ile aynı "sinyal önerebilir, sadece risk/ onaylayabilir"
  ilkesi burada da geçerli).
- Kanıt: `tests/test_portfolio_fusion.py` — ölçekleme faktörünün her iki
  pozisyona da AYNI oranda uygulandığı ve ölçeklenmiş ağırlıkların
  `PortfolioRiskEngine`'e bağımsızca geri verilince gerçekten tam olarak
  `max_var`'ı ürettiği (sadece ölçekleme aritmetiğine güvenilmiyor, ayrıca
  doğrulanıyor) kanıtlanıyor.
- **Gate kanıtı** (roadmap: "3+ varlık sınıfını aynı anda paper-trade eden,
  portföy-VaR limitini gerçekten uygulayan bir entegrasyon testi"):
  `test_three_plus_asset_classes_paper_traded_with_portfolio_var_enforced` —
  4 sembol (BTCUSDT/XAUUSD/NASDAQ/US10Y, ≥3 farklı `AssetClass`) için gerçek
  OHLCV üretilip getiriler hesaplanıyor; dağıtılmış bir tahsis limitin altında
  onaylanıyor, agresif/yoğunlaşmış bir tahsis ise gerçekten ölçekleniyor
  (kod var ama tetiklenmiyor değil — her iki dal da fiilen çalıştırılıp
  doğrulanıyor).
- `pytest -q`: 308 passed.
- **Kapsam dışı bırakılan (bilinçli):** Faz171'in kendi roadmap metninde
  dashboard bağlantısı istenmiyor (Faz167'nin aksine) — bu yüzden dashboard'a
  bağlanmadı. Gerçek çapraz-varlık veri sağlayıcıları (equity/commodity/fx/bond
  borsaları) da yok — sadece deterministik mock veri ile test edildi.

## Mimari Notlar
- **BinderStage kapsamı (Sprint 1 netleştirme, 2026-08-04):** BinderStage bilinçli olarak sadece
  `"wisdom"` tipini `CognitiveBinder.knowledge_to_belief()` ile ayrı bir "bilgi kaynaklı" belief'e
  çeviriyor. `"debate_result"` zaten CouncilStage'in ürettiği ana `belief` (council_belief) için
  destekleyici/açıklayıcı meta veri — Fusion/RecordingStage'e giden asıl belief bu, debate_result'ı
  ayrıca bir belief'e çevirmek aynı karar için iki rakip belief üretir, bu yanlış olur. `"observation"`
  tipini ise şu an hiçbir stage üretmiyor (bkz. borç #8) — üretilmeye başlarsa, doğal yeri BinderStage
  değil `MemoryConsolidator.capture_cycle` (semantic memory consolidation), o da bağlanmalı. Sonuç:
  BinderStage'in kapsamı doğru, önceki "borç" kaydı yanıltıcıydı.
- Risk otoritesi: `GuardrailStage` (erken) + `RiskGateStage` (fusion sonrasi) -- ikili yapi ✅
- `ForwardOutcome`: entry = data[-(n+1)], exit = data[-1]; canlida `pending=True`
- Learning: `finalize()` outcome set edildikten sonra `_persist_and_learn` calisir

- TimescaleDB migration: CI Docker Compose'da çalışıyor, local'de xfail
- E2E testleri: mock → gerçek DB assert çevrildi (test_e2e_persist_chain, test_recording_stage_e2e)

- **Açık borç:** İki beyin yasağı — CognitiveEngine (stage zinciri) vs Orchestrator (RSI shortcut). API `/cycle` belgelenmeli, tercihen Engine tek yol.
- E2E testleri: mock → gerçek DB assert çevrildi (test_e2e_persist_chain, test_recording_stage_e2e)
