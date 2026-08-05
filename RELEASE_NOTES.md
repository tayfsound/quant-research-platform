# v1.9.0 — Faz 183 (Release)

**Tarih:** 2026-08-05
**Kapsam:** ROADMAP_TO_V1.md'deki Sprint 0'dan Faz 182'ye kadar tüm bloklar,
Faz 172 (Execution Layer) hariç.

Bu belge roadmap'in Faz 183 gate'inin karşılığı: "Tag, release notes, son
mimari review." Aşağıdaki liste, roadmap'in kendi Faz 183 tanımındaki
"elinizde olması gereken" maddeleriyle **gerçek durumu** karşılaştırıyor —
"yazıldı" ile "tamamlandı" arasındaki farkı kapatmak bu projenin baştan
beri en çok vurgulanan kuralı olduğu için, burada da abartısız yazılıyor.

## Roadmap'in Faz 183 kontrol listesi — gerçek durum

| Madde | Durum | Not |
|---|---|---|
| Paper trading + gerçek borsa execution | ❌ **Yok** | Faz 172 (Execution Layer) proje sahibinden gerçek (testnet) borsa API key'i bekliyor — bu oturumda kasıtlı olarak dokunulmadı. `exchange_gateway/binance/adapter.py` sadece salt-okunur genel piyasa verisi; emir verme/testnet/paper-live switch mimarisi hiç yok. |
| Replay + Backtest (deterministik, doğrulanmış) | ✅ **Var, gerçekten doğrulandı** | `services/replay_engine.py` (services/replay/'ın gerçek motor haline getirilmiş hali) + `backtest/` (vektörize motor, embargo walk-forward, metrik motoru, Celery worker). Determinizm: aynı pinlenmiş weight snapshot ile iki backtest çalıştırması birebir aynı sonucu üretiyor (gerçek testle kanıtlı). |
| AI Learning + Cognitive Memory + Belief/Debate Engine (gerçekten bağlı, ada değil) | ✅ **Büyük ölçüde** | Bu oturumda kapatılan gerçek "ada" örnekleri: `belief_snapshot_id` hiç set edilmiyordu (artık set ediliyor), `debate_result` sessizce atılıyordu (artık explainability zincirine giriyor), `episodes`/`beliefs`/`observations`/`lessons` tabloları hiçbir migration'da yoktu (artık var). |
| Risk Engine (fusion-öncesi VE fusion-sonrası, ikisi de gerçek) | ✅ | `GuardrailStage` (erken) + `RiskGateStage` (fusion sonrası) — ikisi de gerçek DB'ye karşı test edilmiş entegrasyon testleriyle kanıtlı (bkz. `tests/test_e2e_scenarios.py`). Risk limitleri artık gerçekten DB-backed ve ADMIN-onaylı (`POST /risk-limits`) — üretimde `/cognitive/run` VE `CognitiveOrchestrator.run_cycle()` (iki bağımsız yol) artık gerçek limitlerle çalışıyor, önceden ikisi de her zaman `MISSING_LIMIT` ile reddediyordu. |
| Portfolio Management | ✅ | `risk/limits/portfolio.py` (kovaryans + VaR) + `services/portfolio_fusion.py` — 3+ varlık sınıfı ile gerçek entegrasyon testi. |
| Monitoring + Explainability | ✅ | Prometheus metrikleri artık gerçek kod yollarına bağlı (önceden tamamen dekoratifti). `GET /decisions/{id}/explain` — tam zincir (agent→evidence→belief→debate→risk→weight→outcome), gerçek veriyle kanıtlı. |
| Research Workspace + Plugin System | ✅ | Hash-gated plugin loader + Research Workspace UI — kod değiştirmeden, sadece UI'dan yeni bir agent eklenip çalıştığı gerçek bir testle kanıtlı. |
| API + Auth | ✅ | Gerçek User/Role/API Key/Audit Log altyapısı var, JWT+bcrypt kullanıyor, her yetkilendirme kararı loglanıyor. Tüm REST router'ları artık en az `get_current_user` (VIEWER+) ile korumalı; hesaplama tetikleyen POST'lar (cognitive/run, orchestrator/cycle, backtest/run, strategies/simulate) `require_role(OPERATOR)`, en yüksek riskli olanlar (weight approval, plugin trust/upload) `require_role(ADMIN)`. Dashboard frontend de auth header'larıyla güncellendi. |
| Cloud deployment | ✅ **Gerçek bir K8s cluster'da uçtan uca doğrulandı** | Docker image build edildi, gerçek bir `kind` cluster'a deploy edildi, 5 gerçek bug bulunup düzeltildi (hardcoded DB bağlantısı, eksik Dockerfile, eksik 13 bağımlılık, `.env`'in image'a gömülmesi, yanlış health check'ler, startup/liveness probe hataları). Gerçek bir HTTP isteği gerçek Postgres'e gerçek bir kullanıcı yazdı. |
| Profesyonel UI | ⚠️ **Bilinçli olarak minimal** | Tam "Bloomberg/TradingView" terminal deneyimi kurulmadı — projenin kendi "büyük UI geliştirme yok" kuralıyla çelişiyordu. Bunun yerine 13 view'ı gruplu bir sidebar'a taşıyan minimal bir düzenleme yapıldı. |

## Bu oturumun sayısal özeti

- **34+ commit**, tamamı push edildi (proje sahibi onayıyla).
- Test sayısı: session başında **çöküyordu** (indent hatası yüzünden 19 test
  dosyası collection'da patlıyordu) → **343 passed, 1 xpassed, 0 xfailed**.
  `npm run build` (tsc -b + vite) de artık temiz (önceden belgelenmiş, kalan
  bir tip hatası da bu turda kapandı).
- **~30 gerçek, sessiz bug** bulundu ve düzeltildi — bunların çoğu "kod
  yazıldı ama hiçbir yere bağlanmadı" ya da "test yeşil ama gerçekte hiçbir
  şey kanıtlamıyor" kalıbındaydı (roadmap'in kendi en çok vurguladığı risk).
  Öne çıkanlar: `git_sha` her zaman "unknown" dönüyordu; risk limitleri
  üretimde **iki ayrı bağımsız yolda** hiçbir yerden set edilmiyordu
  (`/cognitive/run` VE `CognitiveOrchestrator.run_cycle()`); `database/
  connection.py` DB bağlantısını sabit kodluyordu (hiçbir env değişkeni/K8s
  Secret'ın hiçbir etkisi yoktu); 5 tablo (weight_approvals,
  experiment_registry, episodes, beliefs, observations, lessons) hiçbir
  migration'da oluşturulmuyordu; iki sahte WebSocket endpoint'i (`random.
  choice`) dashboard'a gerçek AI çıktısıymış gibi veri gönderiyordu.
- Bağımsız bir güvenlik incelemesi çalıştırıldı (6 aday bulgu, hepsi
  bağımsız doğrulamadan geçti, hiçbiri yüksek güven eşiğini geçmedi).
- CI'a otomatik dokümantasyon-tutarlılık kontrolü eklendi.
- Ölü kod temizliği: `services/decision_persistor.py` (production'da hiç
  kullanılmıyordu), `risk/limits/schema.py`, `risk/limits/enforcement.py`,
  `api/websocket/decisions.py` — dördü de silindi.

## Bilinen borçlar (özet — tam liste `AI_MEMORY_SYSTEM/CURRENT_STATE.md`'de)

- Faz 172 (Execution Layer) — gerçek borsa API key'i bekliyor.
- `/auth/register` bootstrap yarışı — production öncesi bir setup-token
  ile kapatılmalı (güvenlik incelemesinde bulundu, güven: 5/10).
- K8s Ingress'te TLS yok — manifest'ler açıkça "template" olarak işaretli.
- `MemoryService.store_episode()` production'da hiçbir yerden çağrılmıyor —
  semantic memory recall şu an boş dönüyor (gap #8'in kapsamına taşındı,
  proje sahibinin "hangi stage çağırmalı" kararı gerekiyor).
- Stress/soak test ve gerçek üçüncü taraf güvenlik denetimi yapılmadı.

## Bu sürümün gerçek anlamı

v1.0 değil — roadmap'in kendi tahminiyle (7-9 ay, tek kişi + AI-destekli)
tek bir günde ulaşılamayacak bir hedef, ve bu oturum başında bu açıkça
konuşuldu. Bu sürüm, Execution Layer hariç roadmap'in geri kalanının
**iddia edilenle gerçekleşen arasındaki makasın kapatıldığı**, gerçek
entegrasyon testleriyle kanıtlanmış bir kontrol noktası.
