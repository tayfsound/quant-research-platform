# Mevcut Durum -- v1.16.0 (P0: Council artık üretimde gerçek piyasa verisi görüyor)

**Tarih:** 2026-08-05
**Branch:** main
**Son commit (HEAD):** bkz. git log — bu oturumun devamı (gerçek feature engineering: signal_engine.py + orchestrator/cognitive.run wiring)
**Test:** 417 passed, 1 xpassed, 0 xfailed. `npm run build` (tsc -b + vite build) temiz.

## P0 — Council'in üretimde neredeyse tamamen kör olması (2026-08-05, aynı oturum)

Proje sahibinin istediği mimari değerlendirme sırasında bulunan, bu
oturumun en kritik bulgusu: `CognitiveOrchestrator.run_cycle()` — sistemin
**tek gerçek üretim giriş noktası** — `ctx.market.features`'a sadece ham
`rsi`/`ema`/`macd` sayılarını yazıyordu. Ama `ContextAdapter.to_technical()`
gerçekten `trend`/`momentum`/`market_structure`/`ema_alignment`/
`volatility_regime` gibi KATEGORİK alanları okuyor — ve **hiçbir kod bu
alanları üretmiyordu**. Üstüne `orchestrator` `"rsi"` (küçük harf)
yazıyordu ama kod tabanının geneli (`CognitiveBinder`, `inner_critic.py`,
`outcome_evaluator.py`, `salience_detector.py`, onlarca test) `"RSI"`
(büyük harf) bekliyordu — case-sensitivity uyuşmazlığı yüzünden RSI de
hiç gerçek değildi.

**Gerçek etki:** 9 oy-veren ajandan, üretimde gerçek veriyle çalışan
sadece **Order Flow** (bu oturumda doğrudan DB'ye bağlandı) ve **Time/
Epistemology** (kendi kendine hesaplıyor) idi. **Technical, Macro,
Sentiment, OnChain, Pattern, Quant — 6 ajan her zaman aynı nötr varsayılan
görüşü üretiyordu, piyasa ne olursa olsun.** Council gerçek bir analiz
yapıyormuş gibi görünüyordu ama büyük ölçüde sabit girdilerle çalışıyordu.

### Yapılan (gerçek, test kanıtlı)
- `market_data/features/signal_engine.py` (yeni) — ham OHLCV geçmişinden:
  - **Technical:** gerçek RSI (case düzeltildi), gerçek MACD signal line
    (eskiden `macd * 0.9` gibi sahte bir yaklaşıklamaydı — Grok'un
    bulduğu, doğrulanan bir sorun — artık gerçek bir EMA9-of-MACD serisi),
    trend (EMA20 vs EMA50), momentum (MACD histogram yönü), market_structure
    (gerçek swing high/low tespiti), ema_alignment, volatility_regime
    (rolling realized vol), volume_confirmation.
  - **Pattern:** break_of_structure/change_of_character/fair_value_gap/
    swing_structure/liquidity_sweep — kesin tanımlı kurallarla gerçekten
    hesaplanıyor (ICT/BOS/CHoCH standart tanımları). `structure_phase`
    (Wyckoff) kasıtlı olarak basitleştirilmiş bir yaklaşım — gerçek Wyckoff
    analizi çok daha derin hacim/fiyat çalışması gerektirir, bu açıkça
    kod içinde belirtiliyor, sofistike bir şeymiş gibi sunulmuyor.
  - **Quant:** zscore, realized_vol_percentile, autocorrelation, Hurst
    exponent (R/S analizi) — standart, kesin tanımlı istatistiksel
    hesaplamalar.
- `services/orchestrator.py`'nin `run_cycle()`'ı ve `api/rest/cognitive.py`'nin
  `POST /cognitive/run`'ı (eskiden TAMAMEN boş bir context kullanıyordu —
  hiç market verisi bile çekmiyordu) artık bu gerçek sinyalleri kullanıyor.
- Kanıt: `tests/test_signal_engine.py` (10 test — elle hazırlanmış,
  gerçekçi osilasyonlu trend serileri üzerinde trend/market_structure/RSI/
  FVG/BOS/Hurst doğrulanıyor) + `tests/test_council_sees_real_market_data.py`
  (gerçek `run_cycle()`/`POST /cognitive/run` çağrısının artık gerçek
  kategorik sinyaller ürettiğini kanıtlıyor).

### P1 incelendi, düşük öncelikli olarak indirgendi: naive/aware datetime
28 yerde naive `datetime.now()`, 9 yerde aware `datetime.now(UTC)` var —
karışık görünüyor ama incelemede (weight_approval TTL, auth revoke, weight
approval expiry) **hepsi kendi tablosunda/alanında tutarlı şekilde naive**
— aynı alanı hem naive hem aware yazan gerçek bir karışıklık yok, 417
testin hiçbiri bunu tetiklemiyor (naive/aware karışsaydı `TypeError`
verirdi, sessiz değil). Gerçek risk sadece sunucu saat dilimi değişirse ya
da dağıtık/çok-sunuculu bir deploy olursa ortaya çıkar — şu an aktif bir
bug değil. Tüm persistence katmanını UTC-aware'e geçirmek büyük, riskli
bir refactor (28+ yer) — şimdilik düşük öncelikli, dokümante edilmiş borç.

### P2: LiveMarketFeed artık gerçekten market_trades'e yazıyor
`exchange_gateway/binance/live_feed.py` hiçbir yerden çağrılmıyordu ve
`MarketSnapshotEvent`'i zorunlu `exchange` alanı olmadan construct
ediyordu (çalıştırılsaydı `ValidationError` verirdi) — sadece event bus'a
publish ediyordu, kalıcı bir subscriber yoktu, hiçbir trade DB'ye
ulaşmıyordu. Düzeltme: `handle_trade_message()` artık `async def`, her
trade'i `MarketDataRepository.save_trade()` ile `market_trades`'e
yazıyor, `side` Binance'ın `"m"` (is-buyer-market-maker) alanından doğru
türetiliyor, çoklu sembol için combined-stream URL'i eklendi
(`LiveMarketFeed(symbols=[...])`). Kanıt: `tests/test_live_market_feed.py`
(5 test) — biri gerçek Binance WS'ine bağlanıp gerçek bir trade alıp
DB'ye yazdığını doğruluyor.

### Dürüstçe kapatılmadı — icat edilmedi
**Macro, Sentiment, OnChain ajanları hâlâ üretimde gerçek dış veri kaynağına
sahip değil** (`inflation_trend`, `fear_greed_index`, `exchange_outflow_24h`
gibi alanları hiçbir gerçek kod set etmiyor). Bunun gerçek çözümü sahte
veri uydurmak değil, gerçek dış kaynaklara bağlanmak — FRED (proje
sahibinden bekleniyor, ücretsiz), Alternative.me Fear&Greed (key gerekmiyor),
on-chain metrik motoru (Infura/Alchemy/Helius key'leri hazır, sadece
kolay/dürüst metrikler — sonraki sprint). Bu üç ajan, o veri kaynakları
bağlanana kadar bilinçli olarak nötr/varsayılan kalacak — fail-closed,
fail-fake değil.

## Dashboard baştan tasarım + gerçek veri (2026-08-05, aynı oturum)

Proje sahibi dashboard'ın tasarımını "basık karanlık mekanik" bulup baştan
istedi: modern, ferah, doğal, keskin köşe yerine katmanlı geçişler, sade
ama sanat eseri gibi bir renk paleti. Ayrıca daha önce placeholder olduğu
belgelenen 4 sayfa (Market Overview, Predictions, Strategies, Risk
Dashboard) gerçek veriye bağlandı.

- **Tasarım sistemi:** `dashboard/src/index.css`'de Tailwind v4 `@theme`
  token'ları — sıcak kağıt-beyazı canvas, tek bir güvenli aksan rengi
  (indigo-violet), sadece gerçek yükseliş/düşüş için kullanılan sage/rose,
  `rounded-xl/2xl`, çok katmanlı yumuşak gölgeler (`shadow-layer-1/2/3`).
  Sistem karanlık modu tercih ediyorsa otomatik koyu palet de tanımlı
  (`prefers-color-scheme`). `dashboard/src/components/ui.tsx` — Card/
  Badge/Button/Input/StatCard/EmptyState/ErrorNote/CodeBlock — 13 view'ın
  hepsi bu ortak bileşenlerle tutarlı hale getirildi.
- **Market Overview** — artık gerçek: `lightweight-charts` (zaten kurulu
  ama hiç kullanılmıyordu) ile gerçek mum grafiği, `GET /market-data/ohlcv`
  (yeni, `market_snapshots`'ı okuyor) + `GET /market-data/order-book`
  (yeni, Faz 186 order book snapshot'larını okuyor) ile besleniyor.
- **Strategies → Agents** — artık gerçek: `GET /agents/` (yeni)
  `AgentRegistry.create_default()`'ın GERÇEKTEN register ettiği 9 oy-veren
  ajanı + 3 eleştirmen/annotator'ı listeliyor — statik/uydurma değil, kod
  değişirse liste de değişir.
- **Predictions** — artık gerçek: `POST /orchestrator/cycle`'ı tetikleyip
  gerçek council sonucunu (direction/confidence/risk_verdict/pnl/features)
  gösteriyor.
- **Risk Dashboard** — artık gerçek: `GET /risk-limits/` (gap #15) +
  `GET /weights/metrics` (approval latency/pending count) — sahte
  sabit sayılar yerine.
- Kanıt: `tests/test_market_data_api.py` (4 test — gerçek DB'ye yazılan bir
  bar'ın API'den geri okunduğu, auth zorunluluğu, agent roster'ın gerçek
  registry'yi yansıttığı) + gerçek Binance verisi altı çözünürlükte
  ingest edilip canlı sunucuya karşı curl ile doğrulandı.

## Auto-bench: sürekli düşük performanslı ajan otomatik devre dışı (2026-08-05)

Proje sahibinin "kötü performans gösteren ajan sistemden elenmeli" fikri —
"stres" metaforu yerine gerçek bir kod mekanizmasına çevrildi:
`SourceReliabilityAgent` artık bir domain art arda `BENCH_AFTER` (5) kez
`BENCH_THRESHOLD` (0.35) altı güvenilirlik gösterirse onu "benched" işaretliyor;
`CouncilOrchestrator.deliberate()` bu durumda `opinion.performance_weight = 0.0`
set ediyor — `effective_influence` (intrinsic_trust × performance_weight)
gerçekten sıfırlanıyor, yani o ajanın oyu nihai karara **hiç katkı vermiyor**.
Opinion listede kalıyor (sessizce yutulmuyor, explainability zincirinde
görünür, caveat olarak işaretleniyor) ve `RECOVERY_THRESHOLD` (0.5) ile
gerçek toparlanma gösterirse otomatik geri dönüyor. Kanıt: `tests/
test_agent_auto_bench.py` — hem benching hem gerçek toparlanma sonrası
geri dönüş uçtan uca doğrulanıyor.

## Market Data Service v0 (2026-08-05, aynı oturum)

`exchange_gateway/binance/adapter.py` (REST) ve `market_data/ingestion/
pipeline.py` gerçek kodlardı ama hiçbir yerden çağrılmıyordu; çağrılsalar
bile `events/message_bus.py` sadece in-memory'di (kalıcı subscriber yok),
`market_snapshots` tablosu da yoktu — veri publish edilir edilmez kaybolurdu.
`contracts/market_data.py::MarketSnapshot` tam bu iş için tasarlanmış, hiç
kullanılmayan bir contract'tı.

- `faz184` migration: `market_snapshots` (OHLCV, doğal composite key) +
  `market_trades`. `faz186`: `order_book_snapshots` (ham order book değil,
  sadece türetilmiş metrikler — saklama maliyeti kararı). Yan bulgu: local
  DB'de `market_snapshots` adında, repo geçmişinde izi olmayan bir "ghost
  table" vardı (risk_limits'te görülen aynı desen) — drop edilip yeniden
  oluşturuldu.
- `MarketDataRepository`: OHLCV upsert (aynı bar tekrar gelirse günceller),
  trade save/list, order book snapshot save/get_latest.
- `IngestionPipeline.ingest_candles()`/`ingest_order_book()`: artık
  gerçekten DB'ye yazıyor. Orijinal kod `MarketSnapshotEvent`'i zorunlu
  `exchange` alanı olmadan construct ediyordu — hiç çalıştırılmamış olduğu
  için yakalanmamış bir `ValidationError`. `BinanceAdapter.get_order_book()`
  aynı sınıf hata — `OrderBookSnapshot` zorunlu `exchange`/`source_version`
  alanları olmadan construct ediliyordu. İkisi de düzeltildi, gerçek
  Binance'a karşı doğrulandı.
- **TradingView webhook:** TradingView klasik API-key modeliyle çalışmıyor
  (Pine Script alert → HTTP POST). `faz185` migration (`external_signals`) +
  `ExternalSignalRepository` + `POST/GET /webhooks/tradingview` (paylaşılan
  secret ile korumalı, boşsa dev modu) + Pine Script şablonu
  (`docs/tradingview_webhook_setup.md`). Gelen sinyal şu an sadece
  saklanıyor — `TechnicalAgent`'a "ikinci görüş" olarak bağlanması ayrı,
  sonraki bir adım.
- **Gerçek, canlı olarak bulunan kritik bug (Manus AI incelemesi,
  doğrulandı):** `BinanceProvider.get_ohlcv()` zaten çalışan bir event loop
  içinden (örn. `/stream/live`'ın async WS handler'ı) çağrılırsa
  `asyncio.run()` `RuntimeError` fırlatıyordu; genel bir `except Exception`
  bunu yutup sessizce mock veriye düşüyordu, üstelik oluşturulan coroutine
  hiç await edilmeden sızıyordu. `_run_coroutine_sync()` eklendi — çalışan
  bir loop varsa coroutine'i ayrı bir thread'de çalıştırıyor. Gerçek
  Binance'a karşı, gerçek bir event loop içinden çağrılarak doğrulandı.

## Agent kalitesi turu 2 — 9 oy-veren ajan + Alter Ego (2026-08-05, aynı oturum)

Proje sahibiyle ChatGPT'nin önerdiği ~16-20 agent listesi tartışıldı, mevcut
kod + önceki agent turu + bu öneriler sentezlenip nihai bir mimari karara
varıldı: `AgentDomain` enum'daki 16 rolün **hepsi** mimaride gerçek bir role
sahip — ama hepsi "oy" değil, doğru role göre.

**5 yeni gerçek oy-veren ajan** (her biri gerçek `contracts/xxx.py` context'i
+ `ContextAdapter.to_xxx()` mapping + `AgentRegistry`'ye register + test):
- **Pattern** — Wyckoff/BOS/CHoCH/FVG/swing structure.
- **Quant** — z-score/Hurst exponent/autocorrelation (rejime göre mean-reversion
  vs momentum bahsi).
- **Order Flow** — gerçek order book verisiyle besleniyor (Faz 186).
  `ContextAdapter.to_order_flow()` diğerlerinin aksine gerçek bir DB okuması
  içeriyor.
- **Time** — dürüstlük ilkesi: kanıtlanmamış "Pazartesi etkisi" gibi yön
  sinyalleri UYDURMUYOR, her zaman WAIT döner, sadece funding/hafta sonu
  riskini işaretler.
- **Epistemology** — yön tahmini yapmaz, veri tamlığını/tazeliğini ölçüp
  zayıfsa yüksek-güvenli bir WAIT ile council'in genel konviksiyonunu
  dengeler.

**Alter Ego Challenger** (`agents/critics/alter_ego.py`) — `agent_debate.py::
_run_cognitive_audit()` zaten bu rolü `self.challengers.get(AgentDomain.
ALTER_EGO.value)` ile arıyordu ama hiç register edilmediği için hep `None`
dönüyordu, `CognitiveAudit` hep boştu. Herd behavior / overconfidence /
confirmation bias'ı gerçek opinion/debate verisinden hesaplayan bir
implementasyon eklendi — bu, "psychology"/"behavioral" domain'lerinin
gerçek karşılığı (ayrı, Sentiment'la çakışan oy-ajanları değil).

**News/Psychology/Behavioral için ayrı ajan yapılmadı** (Sentiment'la ciddi
çakışıyor — aynı veriyi iki kez oylamak "iki beyin" olurdu). **Portfolio**
zaten `PortfolioRiskEngine`/`PortfolioFusionStage` (Faz 171) ile doğru
yerde. **Executive** zaten debate'in sentez çıktısı.

Kanıt: `tests/test_nine_agent_council.py` — 9 ajanın hepsi
`AgentRegistry.create_default()` ile register, gerçek bir council
deliberation'ı tek bir belief'e sentezliyor, Time/Epistemology'nin WAIT
oyları gerçekten kayda geçiyor (sessizce yutulmuyor).

## Üç bağımsız AI incelemesi doğrulandı (Manus/Grok/Kimi, 2026-08-05)

Proje sahibi üç farklı AI'dan (Manus, Grok, Kimi) bağımsız kod incelemesi
istedi, bulguları buraya getirdi. Her iddia gerçek koda karşı tek tek
doğrulandı — körü körüne kabul edilmedi (bu projenin "yazıldı ≠
tamamlandı" ilkesinin AI-review'lara da uygulanması):

**Gerçek ve düzeltildi:**
- Manus: `asyncio.run()` RuntimeError (yukarıda, Market Data Service
  bölümünde).
- Kimi: "çift risk engine çağrısı" — gerçek ama Kimi'nin düşündüğünden
  farklı: `engines/live_executor.py` + `services/execution_router.py` +
  `services/research_engine.py` diye **tamamen ayrı, ikinci bir "cognitive
  pipeline"** vardı (Observation→Knowledge→Belief→Hypothesis→Risk→Decision→
  Execute), **sıfır caller** (grep ile doğrulandı) — `services/
  research_engine.py`'nin kendi `from engines.belief_engine import
  BeliefEngine` importu bile KIRIKTI (`engines/belief_engine.py` diye bir
  dosya hiç yoktu — sadece `services/belief_engine.py` var, farklı bir
  sınıf). Yani bu kod import edilse bile çökerdi. Kesin ölü:
  `services/research_engine.py`, `engines/observation_pipeline.py`,
  `engines/knowledge_builder.py`, `engines/hypothesis_engine.py`,
  `engines/decision_engine.py` silindi. `LiveExecutor`/`ExecutionRouter`/
  `SandboxExecutor` SİLİNMEDİ — `tests/test_agent_capability.py` bunları
  gerçek `CognitiveEngine` çıktısıyla gerçekten test ediyor (mode-izolasyon
  sistemi). Ama `ExecutionRouter`'da bulunan `RiskEngine(secret=
  "production-secret")` hardcoded secret'ı düzeltildi
  (`get_settings().SECRET_KEY`'e) — bu, gap #15'te kurulan gerçek risk limit
  imzalama sistemini tamamen bypass ediyordu.
- Kimi: `.bak` dosyaları (5 tane) ve `test_intelligence_logs/` (git'e
  tracked 11 JSON dosyası) — silindi, `.gitignore`'a eklendi.

**Zaten kapatılmış, review'lar eski bilgiye dayanıyordu:** store_episode/
MemoryEngine (gap #8), RiskChallenger boş context, risk limitlerinin set
edilmemesi.

**UYDURMA (Kimi) — gerçek koda bakılmadan yazılmış, doğrulanınca çürüdü:**
`SECRET_KEY = "change-me"` (yanlış — gerçek placeholder farklı bir metin),
`dashboard/App.tsx` bozuk/kırık (yanlış — dosya tam ve doğru), `dashboard/
api/client.ts`'de hardcoded `http://localhost:8000` (yanlış — aslında
`import.meta.env.VITE_API_URL || ""`, relative URL).

**Manus'un ForwardOutcome bulgusu da yanlış çıktı** — kod gerçek fill
price'ı entry olarak kullanıyor (`if entry_price and entry_price > 0: entry
= entry_price`), tarihsel bar sadece "pending" fallback'i için.

**Ders:** Üç review'un hepsi gerçek CURRENT_STATE.md'yi okuyup güncel kodu
çalıştırmadan yazılmış görünüyor — bazı bulgular kesinlikle değerli
(asyncio bug, ölü ResearchEngine kümesi), bazıları tamamen hayal ürünü.
Doğrulamadan hiçbirine güvenilmemeli.

## Agent kalitesi turu — Council/Debate katmanındaki iki gizli ada kapatıldı (2026-08-05, aynı oturum)

Proje sahibi "agent'ların çalışması konusunda yapabileceğimiz geliştirmeler
var mı" diye sordu — `agents/`+`services/council_orchestrator.py`+
`services/agent_debate.py` incelenirken, tam olarak bu oturumun geri kalanıyla
aynı desende **iki gerçek, üretimi sessizce etkisiz kılan bug** bulundu:

1. **RiskChallenger fiilen hiçbir zaman itiraz üretemiyordu.**
   `CouncilOrchestrator.deliberate()` `self.debate.run_debate(opinions, {})`'ı
   HARDCODED boş bir context ile çağırıyordu. `RiskChallenger.challenge()`'ın
   iki ana kontrolü (`volatility > 0.7`, `crowding_risk > 0.6`)
   `context.get(...)` üzerinden okuduğu için her zaman `0.0`'a düşüyordu —
   eşikleri geçmesi matematiksel olarak imkansızdı. Üçüncü kontrol
   (`data_quality < 0.5`) de ölüydü çünkü 4 gerçek ajanın hepsi
   `data_quality`'yi sabit ≥0.75 raporluyor. Sonuç: roadmap'in vurguladığı
   "risk katmanı kararları eleştirir" mekanizması production'da **hiçbir
   zaman hiçbir şey yapmıyordu.** Düzeltme: `CouncilOrchestrator.
   _build_debate_context()` eklendi — `volatility`'yi gerçek
   `TechnicalContext.volatility_regime`'den, `crowding_risk`'i gerçek
   opinion'ların yön dağılımından (çoğunluk yönü / toplam yönlü opinion)
   hesaplıyor. Kanıt: `tests/test_risk_challenger_context.py` — yüksek
   volatilite + unanimous yön + yüksek confidence senaryosu artık
   gerçekten en az bir `RiskChallenge` üretiyor (öncesinde HİÇBİR girdi
   için üretemezdi).

2. **SourceReliabilityAgent/ReliabilityAnnotator hiçbir yerden çağrılmıyordu.**
   Tam çalışan, kendi testi yeşil bir sınıftı ama hiç entegre edilmemişti —
   her ajanın `source_reliability`'si sonsuza kadar kendi hardcoded
   sabitinde donuk kalıyordu (`TechnicalAgent` hep 0.75, `MacroAgent` hep
   0.9, vb.), gerçek geçmiş performansına göre HİÇ uyarlanmıyordu.
   `source_reliability`, `intrinsic_trust`'ın %20'si ve `BeliefEngine.
   apply_weights()`'in doğrudan kullandığı `effective_influence`'ı
   etkiliyor — yani bu kozmetik değil, gerçek karar ağırlıklandırmasını
   sessizce etkileyen bir eksiklik. `CouncilOrchestrator.__init__`'e
   `self.reliability_annotator = ReliabilityAnnotator()` eklendi,
   `deliberate()` artık her cycle'da opinion'ları annotate edip
   `source_reliability`'yi gerçek geçmiş ortalamaya göre güncelliyor ve
   `.recalculate()`'i tekrar çağırıyor. Kanıt: `tests/
   test_council_reliability_wiring.py` — birkaç düşük-confidence'lı cycle
   sonrası bir ajanın `source_reliability`'sinin artık kendi hardcoded
   varsayılanından farklı olduğu (gerçek geçmişi yansıttığı) doğrulanıyor.

**Yan not — proje sahibiyle konuşuldu, henüz başlanmadı:** Market data
tarafında da aynı desen var — `exchange_gateway/binance/adapter.py`
(REST), `exchange_gateway/binance/live_feed.py` (WS), `market_data/
ingestion/pipeline.py` hepsi gerçek ve çalışır durumda ama **hiçbir
yerden çağrılmıyor**, ve olsalar bile `events/message_bus.py` sadece
in-memory (hiçbir kalıcı subscriber yok, hiçbir OHLCV/tick tablosu yok).
Şu an gerçekte olan: `CognitiveOrchestrator.run_cycle()` her seferinde
tek seferlik, kalıcı olmayan bir REST çekimi yapıyor. Gerçek, sürekli
çalışan, DB'ye yazan bir Market Data Service'in inşası — Execution
Layer'ın aksine testnet key GEREKTİRMİYOR (genel piyasa verisi kimlik
doğrulama istemiyor) — ayrı, sıradaki bir sprint olarak planlandı.

## Gap #8 — MemoryEngine gerçekten kablolandı (2026-08-05, aynı oturum)

`engines/memory_engine.py::MemoryEngine` production'da **hiçbir yerden çağrılmıyordu**
(grep ile doğrulandı — sadece kendi dosyasında tanımlıydı). Onu `CognitiveEngine.finalize()`'a
bağlamaya çalışırken, hiç çalıştırılmamış olmasının **üç ayrı, bağımsız bug**
yüzünden olduğu ortaya çıktı — hiçbiri daha önce hiçbir testte yakalanmamıştı
çünkü hiç kimse bu kod yolunu hiç çalıştırmamıştı:

1. `MemoryEngine.execute()` `self.consolidator.consolidate_if_ready()` çağırıyordu
   ama `MemoryConsolidator`'da böyle bir metod hiç yoktu — ilk çağrıda anında
   `AttributeError`.
2. `MemoryEngine.execute()` `self.consolidator.working.observations`'a erişiyordu
   ama `MemoryConsolidator.__init__` hiçbir zaman bir `WorkingMemory` kurmuyordu —
   ikinci bir `AttributeError`.
3. `MemoryConsolidator.commit_to_episodic()` **her çağrıda `self.episodic.episodes`
   listesinin TAMAMINI** (DB'den restore edilen 100 eski episode dahil) yeniden
   `INSERT` ediyordu — tek seferlik bir batch-yükleme varsayımıyla yazılmış, ama
   canlı pipeline'a bağlanınca her cycle'da restore edilen geçmişi + önceden zaten
   kaydedilmiş episode'ları tekrar tekrar duplicate satır olarak yazacaktı (composite
   PK `(id, created_at)` farklı `created_at` ile aynı `id`'yi kabul ediyor —
   sessizce çoğalan satırlar, tespit edilmesi zor bir veri bütünlüğü sorunu).

Üçü de düzeltildi: `consolidate_if_ready()` eklendi (`SemanticMemory.consolidate()`'e
delege ediyor), `MemoryConsolidator.__init__`'e gerçek bir `WorkingMemory` eklendi
(`capture_cycle()` artık gerçek bir working-memory observation'ı da ekliyor),
`commit_to_episodic()` artık `_committed_ids` ile sadece YENİ episode'ları yazıyor.
Ayrıca (gap #16 ile aynı kök neden) `commit_to_episodic()` artık her save'den önce
`EmbeddingService.encode_episode()` çağırıp gerçek bir embedding yazıyor — önceden
hep `None` yazılıyordu, semantic search hiçbir şey bulamıyordu.

`CognitiveEngine.__init__`'e `self.memory_engine = MemoryEngine()` eklendi,
`finalize()`'a (`run()`'a değil — backtest'ler `run(persist=False)` çağırıp
hiç `finalize()` çağırmıyor, yani binlerce sentetik bar için gereksiz embedding/DB
yazımı olmuyor) `if ctx.outcome is not None: self.memory_engine.execute(ctx)` eklendi.
`services/orchestrator.py`'nin `run_cycle()`'ı zaten `finalize()`'ı çağırıyordu
(`/orchestrator/cycle`, `/dashboard/latest`, `/stream/live`) — üçü de artık her
gerçek cycle'da gerçek bir episodic memory satırı yazıyor.

Kanıt: `tests/test_memory_engine_wiring.py` — iki ardışık gerçek `run_cycle()`
çağrısı tam olarak 2 yeni (duplicate değil) episode yazıyor, ikisi de gerçek
embedding'le; ayrıca gerçek bir cycle'ın yazdığı episode'u semantic search'ün
gerçekten bulduğu ayrıca kanıtlanıyor.

## Auth bootstrap yarışı kapatıldı (2026-08-05, aynı oturum)

Güvenlik incelemesinin bulduğu (güven 5/10) `/auth/register`'da ilk kaydolanın
otomatik ADMIN olması riski: `ADMIN_SETUP_TOKEN` env değişkeni eklendi (boşsa
eski davranış aynen devam ediyor — local dev/test'i bozmuyor). Set edilmişse,
ilk (bootstrap) kayıt `setup_token` alanında doğru değeri göndermek zorunda,
yoksa 403. Kanıt: `tests/test_auth_bootstrap_token.py` (3 test: yanlış token
reddedilir, doğru token ADMIN olarak kabul edilir, token hiç set edilmemişse
davranış değişmez).

## Faz 183 sonrası temizlik turu (2026-08-05, aynı oturum)

Roadmap'in kendi Faz 183 gate'i (RELEASE_NOTES.md) kapandıktan sonra, proje
sahibi "bütün planlamayı tamamlayalım" dedi — geriye kalan gerçek, dokümante
edilmiş borçlar (Execution Layer hariç, o proje sahibinin testnet key'ini
bekliyor) üzerinde çalışıldı:

### Gap #7 — dokümantasyon sürüklenmesi düzeltildi
`weight_approvals` tablosu zaten Faz 182'de kapatılmıştı ama Bilinen Borçlar
tablosundaki satır güncellenmemiş kalmıştı — dokümantasyon sürüklenmesinin
kendisine bir örnek. Satır düzeltildi.

### Gap #12 — İki DecisionPersistor sınıfı: tek sınıfa indirildi
`services/decision_persistor.py` production'da **hiçbir yerden import
edilmiyordu** (sadece 2 test dosyası kullanıyordu) — `database/repositories/
decision_persistor.py` (gerçek üretim yolu, `DecisionRecorder` üzerinden)
zaten kazanmıştı, kanıt netti. Silindi; `tests/test_feedback_loop.py` ve
`tests/test_faz164_replay_determinism.py` gerçek sınıfa taşındı.

### Gap #15 (P0) — risk limit'ler: gerçekten kapatıldı, İKİ ayrı yerde
**Bu oturumun en önemli bulgusu.** Üç değil, gerçekte **beş** farklı "risk
limit" temsili vardı: `risk/limits/schema.py::RiskLimit` (pydantic,
`.verify()` yok, hiçbir yerde kullanılmıyor), `risk/limits/enforcement.py::
RiskLimit`/`RiskEnforcer` (dataclass, sadece kendi testinde kullanılıyor),
`contracts/risk.py::RiskLimit`/`RiskGatePort` (aspirational port tasarımı,
hiçbir yerde implement edilmemiş), ve gerçek kazanan:
`contracts/contexts/risk.py::RiskLimitEntry` (`RiskContext.limits`'in
gerçek pydantic tipi, çalışan bir `.verify(secret)` metodu var, `RiskEngine`
zaten bunu bekliyor). İlk üçü dead code olarak silindi (`risk/limits/
schema.py`, `risk/limits/enforcement.py`, `tests/test_risk.py` — canlı kalan
`VolatilityCircuitBreaker` testi `tests/test_circuit_breakers.py`'a taşındı).

Eksik olan gerçek parça: `RiskLimitEntry`'yi DB'ye kalıcı, ADMIN-onaylı
(Faz 160: "insan onayı zorunluluğu") yazan bir tablo/repository/endpoint hiç
yoktu. Eklendi:
- `database/migrations/versions/faz172_risk_limits_table.py` — yan bulgu:
  local dev DB'de zaten adı `risk_limits` olan, repo geçmişinde hiçbir
  SQLAlchemy modeli olmayan, boş (0 satır), FK'sız bir "ghost table" vardı
  (weight_approvals/episodes'ta görülen aynı desen) — güvenle drop edilip
  gerçek şemayla yeniden oluşturuldu.
- `database/repositories/risk_limit_repository.py` — `RiskLimitRepository`
  (Class 2: save/get_active/list_active) + `load_active_limits()` — **tek,
  paylaşılan** yükleyici fonksiyon.
- `api/rest/risk_limits.py` — `POST /risk-limits/{limit_type}` (ADMIN,
  SECRET_KEY ile imzalar), `GET /risk-limits/` (VIEWER).
- `services/cognitive_engine.py`: `RiskEngine(secret=get_settings().SECRET_KEY)`
  — eskiden hep boş secret'la kuruluyordu, imza doğrulaması hiçbir zaman
  gerçek anlamda çalışmıyordu.

**Gerçek bug, iki ayrı üretim yolunda, ikisi de bulunup düzeltildi:**
1. `api/rest/cognitive.py` `POST /cognitive/run` — `ctx.risk.limits` hiç
   doldurulmuyordu, `RiskEngine` her zaman `MISSING_LIMIT` ile reddediyordu.
2. `services/orchestrator.py` `CognitiveOrchestrator.run_cycle()` — **aynı
   bug, bağımsız olarak** — bu fonksiyon `/orchestrator/cycle`,
   `/dashboard/latest` ve (bu turda gerçeğe bağlanan) `/stream/live`'ın
   arkasındaki gerçek motor, kendi `ctx.risk.limits`'ini de hiç
   doldurmuyordu. `self.max_position_size`/`max_drawdown_limit` constructor
   argümanları da risk gate'e hiçbir zaman bağlanmamıştı (dead parametreler).
   İkisi de artık `load_active_limits()`'i çağırıyor.

Kanıt: `tests/test_risk_limits_api.py` (gerçek HTTP: ADMIN limit set eder →
`POST /cognitive/run` artık `MISSING_LIMIT` içermiyor; OPERATOR limit
set edemez → 403) + `tests/test_orchestrator_risk_limits.py` (aynısı
`CognitiveOrchestrator.run_cycle()` için).

**Fail-closed davranış korundu:** hiç limit set edilmemişse `ctx.risk.limits`
boş kalır, `MISSING_LIMIT` hâlâ doğru, kasıtlı davranış — taze bir
deployment hiçbir gerçek limite karşı sessizce trade onaylamamalı.

### Gap #16 — embedding_service: gerçek testle kanıtlandı
Kök neden bulundu: `sentence_transformers`'ın `encode()`'u `self.device`'ı
model parametrelerinden okuyor; standart `patch("transformers.AutoModel/
AutoTokenizer.from_pretrained")` deseni (LLM reasoner testlerinde kullanılan)
bunu bir `MagicMock`'a çeviriyor, `self.to(device)` `TypeError` patlıyor.
Çözüm kod tarafında değil — `EmbeddingService`/`SemanticSearch` yerel
cache'teki gerçek `all-MiniLM-L6-v2` ile (ağ gerekmeden) doğru çalışıyor,
sadece bu testlerde o mock'u UYGULAMAMAK gerekiyor. `tests/
test_embedding_semantic_search.py`: gerçek 384-boyutlu normalize vektör +
gerçek pgvector benzerlik araması, gerçek DB'ye karşı.

**Yan bulgu (kapatılmadı, gap #8'in bir uzantısı olarak belgeleniyor):**
`MemoryService.store_episode()` — ve dolayısıyla `EmbeddingService.
encode_episode()` — production'da **hiçbir yerden çağrılmıyor**. Yani
episode'lar hiç embedding'siz kaydediliyor (zaten hiç kaydedilmiyorlar,
gap #8), semantic memory recall şu an production'da tamamen boş dönüyor.
Bu, gap #8'in kapsamına giren, proje sahibinin "hangi stage capture_cycle'ı
çağırmalı" kararını gerektiren ayrı bir iş — burada sadece netleştirildi.

### Gap #18 — Sprint 21 (REST+WS): iki sahte WS endpoint gerçeğe bağlandı
`api/websocket/decisions.py` ve `api/websocket/live_predictions.py`
**tamamen uydurma veri** üretiyordu (`random.choice`/`random.uniform`) —
`LivePredictions.tsx` bunu gerçek bir model çıktısıymış gibi gösteriyordu.
- `decisions.py`: hiçbir frontend dosyası tarafından hiç çağrılmıyordu —
  silindi (dead code).
- `live_predictions.py`: gerçek `CognitiveOrchestrator.run_cycle()`'a
  bağlandı (aynı motor, `/orchestrator/cycle`/`/dashboard/latest` ile
  paylaşılıyor — `services/orchestrator.py`'nin dönüş sözlüğüne
  `confidence`/`features`/`symbol` eklendi).
- **Ayrı bir gerçek bug:** `live_predictions.router` `/api/v1` prefix'i
  altında kayıtlıydı ama `LivePredictions.tsx` `ws://localhost:8000/stream/
  live`'a (prefix'siz) bağlanıyordu — gerçek bir tarayıcıda bu asla
  bağlanamazdı (404). Düzeltildi: `/api/v1/stream/live`.
- **Ayrı, önceden belgelenmiş bir build hatası de bu turda kapandı:**
  `AIReasoning.tsx`/`LivePredictions.tsx`'te `useState(null)` tip
  çıkarımının `never`'a düşmesi yüzünden `npm run build` (`tsc -b`) fail
  ediyordu (gap #14'te not edilmişti, atlanmıştı) — `useState<any>(null)`
  ile düzeltildi, `npm run build` artık temiz.
- Kanıt: `tests/test_live_predictions_ws.py` — gerçek WS bağlantısı, gerçek
  orchestrator cycle verisi (mock'suz — embedding path'i gerçek çalışması
  gerekiyor, gap #16 ile aynı sebep).

## Faz 183+ — Auth: kalan ~12 router'a yayılım, gap #17 kapatıldı (2026-08-05)
Faz 178-179'da bilinçli olarak ertelenen "TÜM endpoint'lere auth" işi
tamamlandı. `api/rest/cognitive.py`, `orchestrator.py`, `dashboard.py`,
`memory.py`, `models.py`, `reasoning.py`, `strategies.py`, `audit.py`,
`experiments.py`, `explainability.py`, `replay.py`, `backtest.py` — hepsine
`Depends(get_current_user)` (salt-okuma, VIEWER+) ya da
`Depends(require_role(Role.OPERATOR))` (gerçek hesaplama tetikleyen POST'lar:
cognitive/run, orchestrator/cycle, dashboard/latest, strategies/simulate,
backtest/run, backtest/run-async) eklendi. `weights.py` ve `workspace.py`
zaten korumalıydı (Faz 178-179).

Bunu bozan 6 test dosyası (`test_api_orchestrator.py`, `test_dashboard_api.py`,
`test_celery_tasks.py`, `test_experiment_registry_real_persist.py`,
`test_explainability_chain.py`, `test_replay_decision_api.py`)
`tests/auth_helpers.py`'ın `make_authed_headers()` yardımcısıyla güncellendi.

Bu değişiklik dashboard frontend'ini de kırıyordu — `dashboard/src/api/client.ts`
(`fetchLatestCycle`) ve 5 view (`AIReasoning.tsx`, `DecisionExplain.tsx`,
`BacktestRuns.tsx`, `ExperimentList.tsx`, `ReplayView.tsx`) artık-korumalı
endpoint'leri `authHeaders()` olmadan çağırıyordu (401 alırlardı). Hepsine
`dashboard/src/api/auth.ts`'deki `authHeaders()` eklendi; `npx tsc --noEmit`
temiz.

`pytest -q`: 340 passed, 1 xpassed (backend); gap #17 artık kapalı.

## Faz 182 — Güvenlik incelemesi (2026-08-05)
Bu oturumdaki 26 commit'lik diff (auth sistemi, plugin loader, Celery,
K8s manifest'leri dahil) üzerinde bağımsız bir güvenlik incelemesi
(`security-review` skill'i, 6 paralel doğrulama alt-görevi) çalıştırıldı.
**6 aday bulgu tespit edildi, hepsi bağımsız doğrulamadan geçti, hiçbiri
yüksek güven eşiğini (≥8/10) geçmedi** — yani şu an "acil düzeltilmeli"
diyebileceğimiz somut bir güvenlik açığı yok. En değerli bulgu (güven: 5/10,
düzeltilmesi önerilir ama acil değil): `/auth/register`'da ilk kaydolan
kullanıcı otomatik ADMIN oluyor ve sonradan rol yükseltme endpoint'i yok —
bilinçli bir bootstrap deseni (kod yorumunda açıklanıyor) ama gerçek bir
prod dağıtımından önce tek kullanımlık bir setup token'ıyla kapatılması
önerilir. Diğer 5 bulgu (plugin trust endpoint'inde path traversal,
`__init__.py` üzerinden hash-gate bypass, login timing side-channel, Redis
auth'suzluğu, Ingress'te TLS eksikliği) doğrulamada ya gerçek bir
exploit yolu bulunamadığı ya da zaten bilinen/belgelenmiş kapsam
kararlarıyla (örn. ~30 endpoint'in bilinçli olarak auth'suz bırakılması,
gap #17) çakıştığı için elendi.

## Faz 181 — Final UI: bilinçli olarak minimal tutuldu (2026-08-05)
Roadmap tam bir "Bloomberg/TradingView/Cursor/VSCode/Notion karışımı"
profesyonel terminal deneyimi istiyor — bu, projenin kendi AGENT_MEMORY
kuralıyla ("UI büyük geliştirme yok") doğrudan çelişiyor. Proje sahibiyle
netleştirildi: tam terminal UI'ı KURULMADI, bunun yerine mevcut 13 view'ı
(bu oturumda eklenenler dahil) tek satırlık, taşma riski olan bir tab
listesinden gruplu bir sidebar'a taşıyan minimal bir düzenleme yapıldı:
- `dashboard/src/components/Sidebar.tsx` — Live / Research / Risk & Ops
  olarak gruplanmış, sabit genişlikte sol menü. Eski `NavBar.tsx` (13
  buton tek satırda — gerçek kullanımda taşardı) kaldırıldı, hiçbir yerde
  kullanılmıyordu.
- `App.tsx` flex layout'a geçti (sidebar + içerik alanı).
- **Kapsam dışı bırakılan (bilinçli):** gerçek bir "terminal" deneyimi
  (çoklu panel, sürükle-bırak, canlı grafik widget'ları vb.) — bu, roadmap'in
  kendi tahmini gibi ayrı, büyük bir iş. Mevcut 13 view'ın kendisi de
  yeniden tasarlanmadı, sadece nasıl gezinildiği değişti.
**Not:** Faz 172 (Execution Layer) hâlâ bekliyor — gerçek (testnet) borsa API key'i proje sahibinden bekleniyor.

## Faz 180 — gerçek `kind` cluster'da uçtan uca doğrulama (2026-08-05)

`k8s/README.md`'de "postgres/redis Ready oldu ama api/worker doğrulanamadı"
yazıyordu — bu oturumda tamamlandı. Yerel bir `kind` cluster'a gerçekten
deploy edilip **5 gerçek, art arda bulunan hata** düzeltildi (her biri
gerçek pod loglarından teşhis edildi, tahmin değil):

1. `imagePullPolicy` eksikti — `:latest` tag'i K8s'i var olmayan bir
   registry'den çekmeye zorluyordu. `IfNotPresent` eklendi.
2. Worker `celery: executable file not found` ile crashlooped — image
   celery pyproject.toml'a eklenmeden önce build edilmişti. Yeniden build.
3. **`.dockerignore` hiç yoktu** — `COPY . .` yerel `.env` dosyasını
   (gerçek dev DB kimlik bilgileriyle) doğrudan image'a gömüyordu. Bu hem
   gerçek bir secrets-hijyeni sorunu hem de `database/connection.py`
   düzeltmesinin container içinde etkisiz görünmesinin sebebiydi (image
   HÂLÂ eski/gömülü `.env`'i içeriyordu, düzeltme image'a hiç girmemişti —
   iki ayrı build denemesi bunu ortaya çıkardı). `.dockerignore` eklendi.
4. api pod'u `startupProbe` olmadan liveness probe'un `initialDelaySeconds`'ı
   dolmadan (ML modelleri yüklenirken) "unhealthy" sayılıp sürekli
   yeniden başlatılıyordu — `startupProbe` eklendi (150s'ye kadar tolerans).
5. worker `livenessProbe`'unda `celery@$(HOSTNAME)` — K8s exec probe'ları
   shell üzerinden çalışmadığı için `$(HOSTNAME)` hiç genişletilmiyordu,
   literal string olarak geçiyordu, hiçbir zaman eşleşen bir worker
   bulamıyordu. `sh -c` ile sarmalandı.

**Bunların hiçbiri "manifest'i yazdım, muhtemelen çalışır" değildi —
her biri gerçek pod crash log'undan bulundu ve gerçek bir yeniden deploy'la
doğrulandı.** Son durum: `api` (2/2 Ready, 0 restart), `worker` (2/2 Ready,
0 restart), `postgres`/`redis` (8+ saat kararlı). **Gerçek bir HTTP isteği**
(`kubectl port-forward` + `curl`) ile `/health`, `/ready` (`"database":true`
— gerçek DB kontrolü çalışıyor), ve `POST /auth/register` (gerçek bir
kullanıcı, gerçek Postgres'e, Service üzerinden) uçtan uca doğrulandı.

### Yan bulgu: migration borcu 4 tablo daha genişledi
K8s postgres'ini migrate ederken `episodes` tablosunun olmadığı ortaya
çıktı — `MemoryConsolidator` API başlangıcında bunu okumaya çalışıp
crashlooped. `f8fa21f0e94a_reconcile_initial_memory_schema.py` migration'ı
bunu KENDİ docstring'inde zaten itiraf ediyordu: *"Tables already exist
from legacy initialization: observations, episodes, beliefs, experiments,
lessons... No DDL changes applied."* — yani sorun biliniyordu ama hiç
çözülmemişti. `faz171_memory_tables.py` eklendi: `episodes`/`observations`
(gerçek DB'dekiyle birebir aynı — composite `(id, created_at)` PK,
zaten hypertable), `beliefs`, `lessons`. Boş scratch DB'de doğrulandı;
gerçek local dev DB'de tablolar zaten var olduğu için (`alembic stamp
faz171`) — DDL'i tekrar çalıştırmadan hizalandı; K8s postgres'inde
gerçekten `CREATE TABLE` ile çalıştırıldı (orada gerçekten yoktu).
Tek head hâlâ `faz171`.
**Migration testi gate'i artık gerçekten tam:** roadmap'in Faz 182'de
istediği "Alembic geçmişinin tamamının sıfırdan bir DB'de sorunsuz
uygulanabildiği" — 3 farklı boş DB'de (2 scratch container + 1 K8s pod)
doğrulandı.

pytest -q: 340 passed, 1 skipped, 1 xpassed, 0 xfailed (değişmedi — bu
tablolar zaten local dev'de vardı, testler hep yeşildi; asıl kanıt K8s'te).

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
| 8 | ~~`engines/memory_engine.py` hiçbir yerden çağrılmıyor — gerçek ada.~~ **KAPANDI** (2026-08-05, bkz. "Gap #8 — MemoryEngine gerçekten kablolandı"): `CognitiveEngine.finalize()`'a bağlandı, üç bağımsız gizli bug (`consolidate_if_ready` yoktu, `working` yoktu, `commit_to_episodic` duplicate satır üretiyordu) düzeltildi, gerçek embedding'le kanıtlı. `relevant_knowledge`'daki `"observation"` tipi hâlâ hiçbir stage tarafından üretilmiyor (zararsız, ayrı bir P2 — bir gün üretilmeye başlarsa `semantic.consolidated_beliefs`'e taşınması zaten çalışıyor). | ~~P2~~ **Kapandı** | — |
| 6 | Alembic history'de 2 head var: `faz165` (0005 zincirinden) ve `faz161` (f8fa21f0e94a zincirinden, hiç merge edilmedi). `faz161`'in `create_hypertable()` çağrıları local DB'de `decisions`/`experiment_registry`/`weight_approvals` tabloları dolu olduğu için başarısız oluyor (`migrate_data=>true` gerekiyor — Timescale, boş olmayan tabloyu varsayılan olarak hypertable'a çevirmiyor). Bu bir alan/version eksikliği değil, gerçek veri var. CI'da DB boş başladığı için sorun yok. Local'de düzeltmek için: ya `migrate_data=>true` ile devam et (veri kaybı yok ama chunk'lara bölünür), ya da local DB'yi sıfırdan kurup migration zincirini baştan çalıştır. | P2 | Migration testi (roadmap Faz 182 gate) |
| 7 | ~~`weight_approvals` tablosunun kendisi migration zincirinde hiçbir yerde `CREATE TABLE` ile oluşturulmuyor.~~ **KAPANDI** (bu tablo doğrudan Faz 182 bölümünde anlatıldı ama bu satır güncellenmemiş kalmıştı — dokümantasyon sürüklenmesinin kendisine bir örnek): `faz165_base_weight_approvals_table.py` eklendi ve uygulandı. | — | — |
| 9 | ~~İkinci, kopuk Replay motoru~~ **Kapandı (2026-08-04):** Proje sahibi kararı: `services/replay/` gerçek motor, `services/replay_engine.py` bunun üstünde ince facade. Yapılanlar: (1) `engines/replay/replay_engine.py`'deki `DeterministicReplayEngine` düzeltildi — eskiden `decision_engine.evaluate()` snapshot'ı hiç kullanmıyordu ve verification'ı orijinal event'e karşı (yani kendi kendine, tautolojik — hep True) yapıyordu; şimdi `evaluate(snapshot)` restore edilmiş state'i kullanıyor ve replay edilmiş sonucu orijinalin hash'ine karşı doğruluyor (bkz. yeni test: `test_replay_engine_flags_divergence_when_replay_differs`, replay farklı sonuç üretirse `verified=False` gerçekten yakalanıyor). (2) `services/replay_engine.py.replay_decision()` artık `build_snapshot()` + `ReplayVerifier` + `ReplaySeedManager` kullanıyor (eski ad-hoc `hashlib`+global `random.seed()` yerine); dönüş sözlüğüne gerçek `verification` alanı eklendi. (3) `verify_integrity()` — eskiden var olmayan bir `integrity_hash` DB kolonuna karşı kıyaslıyordu, yani her zaman `False` dönen ölü kod idi; artık `replay_decision()`'ı çağırıp gerçek hash doğrulamasını delegize ediyor. (4) Yan bulgu: real-DB replay path'inde `ctx.decision.proposed_direction` restore edilirken sadece `proposed_direction` anahtarına bakıyordu ama gerçek DB satırında bu alan `direction` — yani gerçek kayıtlarda yön hiç restore edilmiyordu (sadece mock'lu testler çalışıyordu); `direction` fallback eklendi. Kanıt: `tests/test_faz164_replay_determinism.py::test_persist_then_replay` artık `result["verification"]["verified"] is True`'yu gerçek DB'ye karşı assert ediyor. `pytest -q`: 269 passed. | ~~P1~~ **Kapandı** | — |
| 10 | **`api/rest/replay.py` iki endpoint'i de (`/sessions`, `/{session_id}`) hiç çalışmıyordu** — `ReplayEngine()` repo'suz (`belief_repo=None, decision_repo=None`) instantiate ediliyordu, her çağrı `{"error": "repositories_not_configured"}` dönüyordu. `SessionFactory` ile gerçek `BeliefRepository`/`DecisionPersistor` enjekte edildi; yeni `POST /replay/decision/{id}` endpoint'i eklendi (tek karar için gerçek hash-doğrulamalı replay). Kanıt: `tests/test_replay_decision_api.py` — gerçek DB'ye kaydedilmiş bir karar, gerçek HTTP çağrısıyla replay edilip `verification.verified=True` dönüyor. | ~~P1~~ **Kapandı** | — |
| 11 | `database/repositories/decision_persistor.py` (production'ın gerçekten kullandığı, `DecisionRecorder` üzerinden) `market_snapshot`'ı `agent_contributions`'a hiç yazmıyordu — `services/decision_persistor.py` (sadece testlerin kullandığı, farklı bir kopya) yazıyordu. Sonuç: gerçek kaydedilmiş kararlarda replay'in snapshot restore'u hep boş dönüyordu. `market_snapshot` append'i eklendi, doğrulandı (`snapshot_restored: True`). **Kapatılmadı, ayrı borç olarak kaldı (#12): iki ayrı `DecisionPersistor` sınıfı var, tek kaynağa indirilmedi** — bu proje sahibinin kararını gerektiren bir "iki beyin" durumu, replay motoru kararına benzer. | ~~P1~~ (snapshot fix) **Kapandı** | — |
| 12 | **İki ayrı `DecisionPersistor` sınıfı var:** `database/repositories/decision_persistor.py` (gerçek üretim yolu — `DecisionRecorder` bunu kullanıyor, `list_recent`/`get_by_symbol`/`outcome` kolonu/`ON CONFLICT DO NOTHING` var) ve `services/decision_persistor.py` (sadece testlerin ve eski replay kodunun kullandığı, `list_recent` yok, `outcome` yazmıyor). API artık production'ın kullandığı (`database/repositories/...`) sınıfa bağlandı (replay, deneyler). Hangi sınıfın kalacağına — ya da `services/decision_persistor.py`'ın tamamen kaldırılıp testlerin de `database/repositories/...`'a taşınmasına — karar verilmedi. | P1 | Proje sahibi kararı |
| 13 | **`experiment_registry` tablosu hiçbir migration'da `CREATE TABLE` ile oluşturulmuyordu — Faz 159'dan beri her `ExperimentRegistryRepository.save()` çağrısı `RecordingStage.execute()`'daki çıplak `except Exception: pass` içinde sessizce patlıyordu.** Yani "ExperimentRegistry bound to RecordingStage" iddiası hiçbir zaman gerçek bir DB satırı üretmemişti. `faz166_experiment_registry_table.py` migration'ı eklendi ve uygulandı; `GET /api/v1/experiments/` de aslında `{"experiments": []}` döndüren bir placeholder'dı (`repo.get_by_git_sha("")` çağırıp sonucu atıyordu) — `ExperimentRegistryRepository.list_recent()` eklendi, endpoint gerçek veriyi dönüyor artık. Kanıt: `tests/test_experiment_registry_real_persist.py` — gerçek bir cognitive cycle çalıştırılıp API'den gerçek (non-"unknown") git_sha ile geri geldiği doğrulanıyor. | ~~P0~~ **Kapandı** | — |
| 14 | **Sprint 2 dashboard gate kapandı (2026-08-04):** `LatestCycle`, `PendingApprovals`, `ExperimentList` bileşenleri Faz 164'te yazılmış ama `App.tsx`'e hiç import edilmemiş/render edilmemişti — NavBar'da sekmeleri bile yoktu, tarayıcıdan asla erişilemiyorlardı. Üçü de artık `App.tsx`/`NavBar.tsx`'e bağlı (`cycle`/`approvals`/`experiments` sekmeleri). Yeni `ReplayView.tsx` eklendi (`POST /replay/decision/{id}` tetikler, `verification.verified`'ı gösterir) — roadmap'in "tarayıcıdan replay tetiklenip aynı sonucu üretebiliyor mu" gate'i buna karşılık geliyor. Doğrulama: `vite dev` sunucusu ayağa kalktı, `App.tsx`'in transpile edilmiş halinde `ReplayView` gerçekten yükleniyor (curl ile doğrulandı); gerçek bir tarayıcıda tıklama testi yapılmadı (bu ortamda tarayıcı yok) ama backend endpoint'i ayrıca gerçek DB'ye karşı test edildi (`test_replay_decision_api.py`). **Önceden var olan, ilgisiz bir sorun:** `npm run build` (`tsc -b`) `AIReasoning.tsx` ve `LivePredictions.tsx`'te bu oturumdan önce var olan tip hatalarıyla başarısız oluyor (muhtemelen tipsiz `useState()` → `never[]` çıkarımı); bu dosyalara dokunulmadı, kapsam dışı bırakıldı. | P2 (build hatası) | Hayır (dev server çalışıyor) |
| 15 | ~~🔴 `ctx.risk.limits`'i üretimde hiçbir kod yolu doldurmuyor.~~ **KAPANDI** (2026-08-05, bkz. "Faz 183 sonrası temizlik turu"): DB-backed `risk_limits` tablosu + `RiskLimitRepository` + `POST /risk-limits` (ADMIN) eklendi; hem `/cognitive/run` hem `CognitiveOrchestrator.run_cycle()` (ikisi bağımsız olarak aynı bug'ı taşıyordu) artık `load_active_limits()`'i çağırıyor. Beş temsilden dördü dead code olarak silindi, kazanan `contracts/contexts/risk.py::RiskLimitEntry` tek gerçek implementasyon oldu. | ~~P0~~ **Kapandı** | — |
| 16 | ~~`services/embedding_service.py` hiçbir testte çalıştırılmamış.~~ **Test-altyapısı kısmı KAPANDI** (2026-08-05): `tests/test_embedding_semantic_search.py` gerçek embedding + gerçek pgvector arama kanıtlıyor (kök neden: standart transformers mock'u `self.device`'ı bozuyor, çözüm o mock'u bu testlerde uygulamamak). **Yeni, dar bulgu:** `MemoryService.store_episode()` production'da hiçbir yerden çağrılmıyor — episode'lar embedding'siz (aslında hiç) kaydediliyor, semantic recall boş dönüyor. Bu gap #8'in kapsamına taşındı. | P2 (kalan kısım gap #8'e taşındı) | Gap #8 — hangi stage `capture_cycle`'ı/`store_episode`'ı çağırmalı, proje sahibi kararı |

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

## Faz 172 — Execution Layer: BEKLEMEDE (2026-08-04)
Roadmap'in kendi metninde 🔴 en riskli blok olarak işaretli ("hız değil
doğruluk önceliklendirilmeli — gerçek para riski burada başlıyor").
`exchange_gateway/binance/adapter.py` doğrulandı: sadece salt-okunur genel
piyasa verisi (`https://api.binance.com`, kimlik doğrulama yok, testnet'e
bile bağlı değil) — emir verme/testnet/paper-live switch mimarisi hiç yok.
Secret hijyeni kontrol edildi: ilk commit'te bir `.env` track edilmişti ama
sadece placeholder değerler içeriyordu (gerçek borsa key'leri hep boştu,
`SECRET_KEY` bile "degistirin-cok-gizli-bir-anahtar" placeholder'ıydı) —
gerçek bir sızıntı yok. `.gitignore` artık doğru, `.env.example` temiz,
gitleaks zaten CI'da aktif (`.github/workflows/ci.yml`). Yani ön koşul
karşılanmış durumda, ama gerçek (testnet olsa bile) API key olmadan emir
verme kodu yazılamaz/test edilemez — **proje sahibi kendisi testnet key
sağlayacağını belirtti, o gelene kadar bu blok bekliyor.**

## Faz 173-174 — Monitoring + Explainability (2026-08-04, aynı oturum)

### Sprint 14-15 — Gerçek zamanlı sistem metrikleri
`observability/metrics.py` zaten Prometheus metrikleri tanımlıyordu
(llm_*, risk_*, active_subprocesses, queue_size) ama **hiçbiri hiçbir yerden
`.inc()`/`.observe()`/`.set()` ile çağrılmıyordu** — `/metrics` çıktısında
isimleri görünüyordu ama değerleri hep sıfırdı, `test_health.py` sadece
metrik ADININ metinde geçtiğini kontrol ediyordu, gerçekten hareket ettiğini
değil. Bu oturumda:
- `risk_decisions_total`/`risk_rejections_total` → `engines/risk_engine.py`'nin
  her üç çıkış noktasına (missing limit / diğer red sebepleri / onay) bağlandı.
- `decisions_total` (yeni) → `RecordingStage.execute()`'a bağlandı (decision-per-sec
  buradan `rate()` ile türetilir).
- `learning_updates_total` (yeni) → `LearningLoop.record()`'a bağlandı.
- `api_requests_total`/`api_request_latency_seconds` (yeni) → `api/main.py`'a
  TEK bir middleware ile TÜM endpoint'leri kapsayacak şekilde eklendi (her
  router'ı ayrı ayrı enstrümante etmek yerine).
- `db_query_latency_seconds` (yeni) → `DecisionPersistor.persist()`'e bağlandı.
- `cpu_usage_percent`/`memory_usage_percent` (yeni) → `psutil` ile scrape
  anında ölçülüyor (arka plan thread'i yerine, Prometheus pull modeliyle
  tutarlı). **Yeni bağımlılık:** `psutil>=6.0.0` — hem sistem Python'a hem
  `.venv`'e kuruldu, `pyproject.toml`'a eklendi.
- Kanıt: `tests/test_observability_metrics.py` — her metrik için gerçek bir
  aksiyon (risk red/onay, gerçek cycle, gerçek HTTP çağrısı, gerçek DB
  persist) öncesi/sonrası Prometheus exposition metnini `prometheus_client.parser`
  ile ayrıştırıp değerin gerçekten arttığını kanıtlıyor — sadece metrik
  adının metinde geçmesini değil.

### Sprint 16 — Explainability zinciri
Zincirin çoğu `DecisionEvent` şemasında zaten vardı ama iki gerçek kopukluk
bulundu:
- **`belief_snapshot_id` hiçbir zaman set edilmiyordu.** `RecordingStage`
  belief'i ayrıca `MemoryService.store_belief()` ile kaydediyordu ama
  `DecisionRecorder.record()`'daki `DecisionEvent(...)` çağrısı
  `belief_snapshot_id` alanını hiç doldurmuyordu — yani "hangi belief?"
  sorusu HİÇBİR gerçek karar için cevaplanamıyordu. Düzeltildi:
  `belief_snapshot_id=belief.id`.
- **`debate_result` parametre olarak alınıyor ama tamamen atılıyordu** —
  "hangi debate?" sorusu da cevapsızdı. Artık `agent_contributions`'a
  `{"_type": "debate_result", "data": ...}` olarak ekleniyor.
- `database/repositories/belief_repository.py`'a `get_by_id()` eklendi
  (önceden sadece `get_latest()`/`get_by_direction()` vardı — belirli bir
  karara ait belief'i çekmenin yolu yoktu).
- `services/explainability.py` (`ExplainabilityService.explain()`) — tüm
  zinciri (agents/evidence/belief/debate/risk/weight_snapshot/outcome) tek
  bir yanıtta birleştiriyor. `api/rest/explainability.py`:
  `GET /decisions/{id}/explain`.
- `dashboard/src/views/DecisionExplain.tsx` — decision id gir, zincirin her
  parçası ayrı `<details>` olarak (tıklanabilir/genişletilebilir) gösteriliyor;
  `App.tsx`/`NavBar.tsx`'e bağlandı.
- **Gate kanıtı** (roadmap: "Bir kararın üzerine tıklayınca tam zincirin
  göründüğü, gerçek veriyle çalışan bir demo"): `tests/test_explainability_chain.py`
  — gerçek bir `CognitiveEngine.run()` çalıştırılıp gerçek `/explain`
  endpoint'i çağrılıyor; `chain.belief` artık gerçekten `None` değil (yukarıdaki
  bug'ın kanıtı) ve gerçek id içeriyor.
- `pytest -q`: 316 passed.

## Faz 176-177 — Plugin System + Research Workspace UI (2026-08-04, aynı oturum)

### Sprint 17-18 — Plugin System
`AgentRegistry.create_default()` 4 sabit ajanı elle register ediyordu,
dinamik keşif yoktu. **Güvenlik notu roadmap'te açıkça isteniyordu** ("hangi
plugin'lerin güvenilir kaynaktan geldiğini doğrulayan bir mekanizma
(imza/hash)"):
- `agents/plugin_loader.py` — `discover_plugins()`: `agents/plugins/*.py`
  taranır ama **fail-closed** — bir dosya, SHA256 hash'i `TRUSTED_PLUGIN_HASHES`'te
  (veya kalıcı trust store'da) olmadıkça import bile edilmez. Bu, uzak bir
  imza/PKI sistemi değil (o ayrı, çok daha büyük bir iş) — bir insanın dosyayı
  gözden geçirip hash'ini eklediği yerel bir trust listesi. Dosya
  değiştirilirse (tampered) hash tutmaz, tekrar güvenilmez hale gelir —
  test'le kanıtlı (`test_tampered_plugin_is_skipped_even_with_a_previously_trusted_filename`).
- `AgentRegistry.create_default()` artık `discover_plugins()`'i gerçekten
  çağırıyor (spy testiyle kanıtlı) — varsayılan trust listesi boş olduğu için
  canlı davranış DEĞİŞMEDİ, sadece keşif yolu bağlandı.
- `pytest -q` (bu alt-blok): `tests/test_plugin_loader.py`, 6 test.

### Sprint 19-20 — Research Workspace UI
Roadmap: "Kod değiştirmeden, sadece UI üzerinden yeni bir agent ekleyip
çalıştığını gösteren bir demo." Hash-gate'i bozmadan bunu sağlamak için:
- `services/plugin_trust_store.py` — `agents/plugins/TRUSTED_HASHES.json`'a
  kalıcı, çalışma-zamanında değiştirilebilir bir trust listesi (upload sonrası
  "trust" tıklamak kod değişikliği/deploy gerektirmez).
- `api/rest/workspace.py`: `POST /workspace/plugins/upload` (sadece dosyayı
  yazar, ASLA otomatik güvenmez — dosya adı `^[a-zA-Z0-9_]+\.py$` ile
  kısıtlı, path traversal engellenir, 50KB boyut limiti), `GET /workspace/plugins`
  (liste + trust durumu), `POST /workspace/plugins/{filename}/trust` (hash'i
  kaydeder + `discover_plugins()`'i tekrar çalıştırıp gerçekten yüklendiğini
  doğrular), `POST /workspace/plugins/{filename}/revoke`.
- `dashboard/src/views/ResearchWorkspace.tsx`: dosya adı + kaynak kod textarea'sı,
  upload butonu, plugin listesi + "Review & Trust"/"Revoke" butonları.
  `App.tsx`/`NavBar.tsx`'e bağlandı.
- **Gate kanıtı**: `tests/test_research_workspace.py::test_upload_then_trust_activates_a_new_agent_with_no_code_change` —
  gerçek HTTP upload → trust ETMEDEN önce `discover_plugins()`'in yüklemediği
  doğrulanıyor → trust → **`agents/registry.py`'ye tek satır bile dokunmadan**
  yepyeni bir `AgentRegistry.create_default()` çağrısı yeni agent'ı içeriyor
  ve gerçekten `.analyze()` çalıştırıp beklenen yönü döndürüyor.
- **Kasıtlı olarak yapılmayan:** Roadmap "Faz 168 (Experiment Registry)
  burada devreye girmeli — her yeni eklenen bileşen otomatik bir deney
  olarak kaydedilsin" diyor, ama `ExperimentRegistry` şemasının
  (`git_sha`/`risk_limits_version`/`feature_schema_id`/`prompt_hash`/`model_id`/
  `decision_ids`) hiçbir alanı "bir plugin trust edildi" olayını anlamlı
  şekilde temsil etmiyor — zorla bir alana sıkıştırmak (`model_id=filename`
  gibi) contract'ın anlamını bozardı (C3 ihlali). Bilinçli olarak atlandı;
  gerçek çözüm ExperimentRegistry'ye plugin-tracking alanı eklemek, ki bu
  proje sahibinin şema kararını gerektirir.
- `pytest -q`: 324 passed.

## Faz 178-179 — API + Auth: KISMİ (2026-08-04, aynı oturum) 🔴

Proje sahibiyle kapsam netleştirildi: gerçek altyapı kur + en yüksek riskli
endpoint'lere uygula; TÜM ~35 endpoint'e yaymak ayrı, bilinçli bırakılmış bir
adım (aşağıda). Execution Layer'ın aksine bu blok dış kimlik bilgisi
gerektirmiyordu, bu yüzden kurulabildi.

### Ne kuruldu (gerçek, test edilmiş)
- **Yeni bağımlılıklar:** `pyjwt`, `bcrypt` (hem sistem Python hem `.venv`'e
  kuruldu, `pyproject.toml`'a eklendi) — parola/JWT için sağlam, standart
  kütüphaneler kullanmadan bunu doğru yapmanın yolu yok.
- `contracts/auth.py`: `Role` (VIEWER < OPERATOR < ADMIN, sıralı IntEnum —
  `role >= min_role` doğrudan çalışır), `User`, `APIKey`, `AuditLogEntry`.
  **Workspace** kasıtlı olarak modellenmedi — sistemde başka hiçbir yerde
  multi-tenant kavramı yok (tek global dashboard/DB), Workspace'i yoktan var
  etmek gerçek bir şeyi genişletmek değil icat etmek olurdu.
- `database/migrations/versions/faz168_auth_tables.py`: `users`, `api_keys`,
  `audit_log` tabloları — uygulandı, doğrulandı.
- `services/auth_service.py`: `bcrypt` ile parola hash'leme, `PyJWT` ile
  token üretme/doğrulama (HS256, `.env`'deki `SECRET_KEY`/`JWT_ALGORITHM`/
  `JWT_EXPIRE_MINUTES`), API key üretme (SHA256 — parola değil, zaten
  yüksek-entropili rastgele token, bcrypt'in yavaşlığı gereksiz).
  **Fail-closed:** `SECRET_KEY` boşsa token üretme/doğrulama tamamen
  reddediliyor (boş string ile imzalamak yerine).
  `get_current_user` (Bearer JWT veya `X-API-Key` header'ını çözer) ve
  `require_role(min_role)` (403 + audit) — **her ikisi de her çağrıda
  allow/deny farketmeksizin `audit_log`'a yazıyor** (roadmap: "her
  yetkilendirme kararının loglanması").
- `api/rest/auth.py`: `POST /auth/register` (ilk kullanıcı otomatik ADMIN —
  başka kimlik doğrulanmış aktör yokken bootstrap; sonrakiler VIEWER),
  `POST /auth/login`, `GET /auth/me`, `POST /auth/api-keys`,
  `GET /auth/audit-log` (ADMIN-only).
- **Korumaya alınan endpoint'ler** (agreed scope — en yüksek risk):
  - `api/rest/weights.py`: `/approve`, `/reject`, `/auto-reject` →
    `require_role(OPERATOR)`. `approved_by` artık client'ın gönderdiği
    keyfi bir string değil, **kimliği doğrulanmış kullanıcının username'i**
    — önceden herkes `approved_by=whoever` diyebilirdi, audit bütünlüğü
    buna bağlı.
  - `api/rest/workspace.py`: `/plugins/upload`, `/plugins/{f}/trust`,
    `/plugins/{f}/revoke` → `require_role(ADMIN)` — kod çalıştırma riski en
    yüksek olan yer.
- **Dashboard bağlantısı** (minimal, H4 uyumlu): `Login.tsx` artık gerçek
  bir login/register formu — önceden Vite'ın varsayılan başlangıç şablonu
  (react/vite logoları, "count" butonu) idi, `onLogin` hiçbir kimlik
  doğrulaması yapmadan direkt çağrılıyordu, tamamen dekoratifti. Artık
  `POST /auth/login`'e gerçek istek atıyor, JWT'yi `localStorage`'a
  yazıyor. `dashboard/src/api/auth.ts`: `authHeaders()` helper'ı, SADECE
  artık korumalı endpoint'leri çağıran `PendingApprovals.tsx` ve
  `ResearchWorkspace.tsx`'e eklendi (kapsam anlaşmasıyla tutarlı — tüm
  dashboard'u auth'a bağlamak ayrı bir iş).
- Kanıt: `tests/test_auth.py` (9 test: hash roundtrip, JWT roundtrip +
  tampered token reddi, register bootstrap, login/me, API key kullanımı,
  audit log'un hem allow hem deny kaydettiği, disabled user reddi,
  SECRET_KEY boşken fail-closed) + `tests/test_weight_approval_e2e.py` ve
  `tests/test_research_workspace.py` gerçek auth header'larla güncellendi
  (`tests/auth_helpers.py` — bootstrap sırası bağımsız, doğrudan repository
  üzerinden deterministik kullanıcı oluşturuyor).
- `pytest -q`: 334 passed.

### Bilinçli yapılmayanlar (proje sahibiyle kapsam anlaşması)
| # | Ne | Neden şimdi değil |
|---|----|--------------------|
| 17 | ~~Roadmap'in istediği geri kalan ~30 endpoint (cognitive/run, replay, backtest, experiments, dashboard, vb.) hâlâ auth'suz.~~ **KAPANDI** (bkz. yukarıdaki "Faz 183+" bölümü, 2026-08-05) — tüm router'lar artık en az `get_current_user` (VIEWER+) ile korunuyor. | — |
| 18 | ~~Sprint 21 (REST+WS API yüzeyinin tamamlanması)~~ **Kısmen kapandı** (2026-08-05): iki tamamen uydurma WS endpoint'i (`/stream/decisions` silindi, `/stream/live` gerçek orchestrator cycle'a bağlandı, yanlış frontend URL'i düzeltildi) — bkz. "Faz 183 sonrası temizlik turu". Sprint 24'ün "penetrasyon testi" kısmı hâlâ yapılmadı. | Gerçek üçüncü taraf pentest proje sahibinin kararı |
| 19 | `SECRET_KEY` hâlâ `.env`'deki geliştirme placeholder'ı (`degistirin-cok-gizli-bir-anahtar`) — gerçek sızıntı değil ama **production'a asla bu değerle çıkılmamalı**. | Gerçek rastgele bir `SECRET_KEY` üretmek/rotasyon prosedürü proje sahibinin production dağıtım kararına bağlı. |

## Faz 180 — Cloud/Kubernetes (2026-08-04, aynı oturum)

### Kritik bulgu: uygulama hiçbir zaman gerçekten deploy edilebilir değildi
`database/connection.py` — projenin HER YERDE kullandığı gerçek `engine`/`SessionFactory`
nesnesi — `DATABASE_URL`'i `"postgresql://quant:quantpass@localhost:5432/quantdb"`
olarak **sabit kodluyordu**, `config/settings.py`'nin `DATABASE_URL_SYNC`'ini
(env değişkeninden/.env'den okunan) hiç kullanmıyordu. Yani `.env`, K8s
Secret, Docker Compose environment — hiçbiri `engine`'in nereye
bağlanacağını hiçbir zaman etkilemiyordu; uygulama HER ZAMAN `localhost:5432`'ye
bağlanmaya çalışıyordu. Local dev'de bu tesadüfen doğru olduğu için hiç fark
edilmedi. **Gerçek bir K8s pod'unu (`kind` ile lokal cluster) deploy edip
CrashLoopBackOff'u debug ederken bulundu** — pod `postgres` servisine değil
`localhost`'a bağlanmaya çalışıyordu. Aynı desen daha önce `database/migrations/env.py`'de
de bulunup düzeltilmişti (settings import ediliyor ama hiç kullanılmıyordu) —
bu, aynı hatanın uygulamanın ASIL çalışma zamanı yolundaki, çok daha kritik
hâli. Düzeltildi: `engine = create_engine(settings.DATABASE_URL_SYNC, ...)`.
`pytest -q` yerelde hâlâ 340 yeşil (yerel `.env`'in varsayılanı zaten
`localhost:5432` olduğu için davranış değişmedi) — asıl kanıt gerçek K8s
pod'unun artık `postgres` servisine bağlanabilmesi.

### Sprint 25-26 — Docker → Kubernetes
- `Dockerfile` **hiç yoktu** — `docker-compose.yml` `api` servisi için
  `build: dockerfile: Dockerfile` diyordu ama dosya mevcut değildi,
  `docker-compose up --build` hiçbir zaman çalışmamıştı. Eklendi, gerçekten
  build edildi (`docker build`, doğrulandı).
- **`pyproject.toml`'da 13 gerçek, kullanılan bağımlılık hiç deklare
  edilmemişti** (`alembic`, `prometheus-client`, `sentence-transformers`,
  `scikit-learn`, `torch`, `lightgbm`, `xgboost`, `sortedcontainers`,
  `filelock`, `websockets`, ve daha önce eklenenlerle birlikte `redis`,
  `celery`) — local dev ortamında bunlar "bir şekilde" (muhtemelen elle,
  sistem Python'a) kurulu olduğu için hiç fark edilmemişti. Temiz bir
  Docker build bunu hemen ortaya çıkardı (`ModuleNotFoundError: No module
  named 'prometheus_client'` vb.). Hepsi eklendi ve gerçek build ile
  doğrulandı.
- Dockerfile, BuildKit pip cache mount kullanıyor (`--no-cache-dir` yerine)
  — bağımlılıklar değiştiğinde bile (örn. bu oturumda celery eklendiğinde)
  torch/sentence-transformers gibi >1GB'lık paketlerin sıfırdan
  indirilmesini önlüyor.
- `k8s/`: `namespace.yaml`, `configmap.yaml`, `secret.example.yaml`
  (gerçek `secret.yaml` asla commit edilmemeli — `.gitignore`'a eklendi),
  `postgres.yaml` (StatefulSet+PVC), `redis.yaml`, `api.yaml`
  (Deployment+Service+HPA), `worker.yaml` (Celery worker Deployment+HPA),
  `ingress.yaml`, `README.md`.
- **Gerçek doğrulama:** `kind` (Kubernetes-in-Docker) kuruldu, lokal bir
  cluster ayağa kaldırıldı, manifestler gerçekten `kubectl apply` edildi.
  Bu süreçte iki gerçek manifest hatası bulundu ve düzeltildi: (1) `image:
  qrp-api:latest` + `:latest` tag'i K8s'in varsayılan `imagePullPolicy: Always`'ini
  tetikliyordu, yerel yüklenmiş image'ı yok sayıp var olmayan bir registry'den
  çekmeye çalışıyordu — `imagePullPolicy: IfNotPresent` eklendi. (2) worker
  pod'u `celery: executable file not found` ile crashlooped — image, celery
  pyproject.toml'a eklenmeden ÖNCE build edilmişti (yukarıdaki gerçek DB
  bağlantısı bulgusuyla aynı build). Redis pod'u gerçekten Ready oldu;
  postgres pod'u gerçekten Ready oldu (gerçek veri kaybı olmadan — bkz.
  Faz 182 migration bölümü, aynı doğrulama sürecinde bulunan migration
  zinciri sorunlarını da ortaya çıkardı).
- `/health`, `/ready`, `/live` (`observability/health.py`) üçü de
  **koşulsuz her zaman "ok" dönüyordu** — DB erişilemez olsa bile `/ready`
  "ready" derdi. Bir K8s readiness probe'u buna bağlıysa hiçbir zaman
  gerçek anlamda "hazır değil" diyemezdi. `/ready` artık gerçek bir
  `SELECT 1` yapıyor, DB erişilemezse 503 dönüyor; `/live` bilinçli olarak
  DB'ye bakmıyor (DB kesintisi liveness'ı değil readiness'ı düşürmeli —
  aksi halde K8s, düzeltemeyeceği bir sorun için sağlıklı bir process'i
  öldürüp yeniden başlatır). Kanıt: `tests/test_health_checks.py`.

### Sprint 27 — Worker/Queue mimarisi
- `services/celery_app.py` + `services/tasks.py` — `docker-compose.yml`'de
  Faz başından beri duran ama hiçbir şeyin kullanmadığı Redis'i gerçekten
  kullanan ilk kod. `run_backtest_task`, Sprint 3-6'nın gerçek backtest
  pipeline'ını (aynı `run_and_persist_backtest`) bir worker'da çalıştırıyor.
- `POST /backtest/run-async` + `GET /backtest/tasks/{id}` — dispatch +
  durum sorgulama.
- Kanıt: `tests/test_celery_tasks.py` — `task_always_eager` ile (Celery
  task'larını gerçek worker süreci olmadan test etmenin standart yolu,
  task'ı gerçek Celery çağrı mekanizmasından geçirerek çalıştırır) task
  mantığı + `/run-async` → `/tasks/{id}` uçtan uca zinciri doğrulanıyor;
  ayrıca gerçek lokal Redis'e (docker-compose'daki) broker bağlantısı ayrı
  bir testle kontrol ediliyor (worker süreci gerektirdiği için xfail,
  strict=False — ama bu oturumda gerçekten xpass etti, Redis gerçekten
  erişilebilir).
- `docker-compose.yml`'e `worker` servisi eklendi.

### Sprint 28 — Auto-scaling + health checks
- `k8s/api.yaml` ve `k8s/worker.yaml`'da `HorizontalPodAutoscaler` (CPU/RAM
  hedefli) — api için 2-10 replika, worker için 2-8.
- Health check'lerin gerçek olması (yukarıda) bu sprint'in asıl işiydi —
  sahte bir health check'e bağlı bir auto-scaler/readiness gate, anlamsız
  bir güvenlik hissi verir.

## Faz 182 — Production Candidate (kısmi, 2026-08-04, aynı oturum)

### Migration testi — TAM YEŞİL (roadmap'in kendi gate'i)
K8s doğrulaması sırasında gerçek, boş bir scratch DB (`docker run
timescale/timescaledb`, hiç veri yok) üzerinde **tüm migration zincirini**
çalıştırırken iki gerçek, derin hata bulundu ve düzeltildi:
1. **`weight_approvals` tablosu hiçbir migration'da `CREATE TABLE` ile
   oluşturulmuyordu** (deneyim registry ile aynı borç türü, #13'te
   kapatılmıştı — bu tabloda kapatılmamış kalan ikizi). `faz165_base_weight_approvals_table.py`
   eklendi, `faz165`'in üzerine bağlandı.
2. **faz161'in `create_hypertable()` çağrıları, "tablo boş değil" hatasının
   ALTINDA daha derin bir sorunu maskeliyordu**: TimescaleDB, partition
   kolonunun (`timestamp`) PRIMARY KEY'in bir parçası olmasını şart koşuyor
   — `decisions`/`experiment_registry`/`weight_approvals`'ın üçü de sadece
   `id` üzerinde tekil PK'ye sahipti. Boş bir DB'de bile bu yüzden
   patlıyordu. Düzeltme: PK'yi `(id, timestamp)`'e genişlet, `migrate_data => TRUE`
   ekle. Bu da YENİ bir kırılmaya yol açtı: `decision_persistor.py`'nin
   `ON CONFLICT (id) DO NOTHING`'i artık eşleşen bir constraint bulamıyordu
   (composite PK, tekil `id` constraint'i değil) — 34 test kırıldı, hemen
   yakalandı, `ON CONFLICT (id, timestamp)`'e düzeltildi (id+timestamp ikisi
   de `DecisionEvent` oluşturulurken bir kez set edildiği için dedup mantığı
   bozulmadı).
- **Hem boş scratch DB'de HEM gerçek lokal dev DB'de (4996 decisions, 1028
  experiment_registry, 182 weight_approvals satırı, sıfır veri kaybıyla)
  doğrulandı.** `decisions`/`experiment_registry`/`weight_approvals`
  şu an gerçekten TimescaleDB hypertable'ları — `tests/test_timescale_migration.py`'deki
  bu oturumdan ÖNCEKİ tek `xfail` artık gerçek bir `PASS` (xfail marker'ı
  kaldırıldı, kalması yanıltıcı olurdu).
- `database/migrations/env.py`: `settings = get_settings()` import edilip
  hiç kullanılmıyordu, `alembic.ini`'deki sabit kodlanmış URL her zaman
  kazanıyordu — yani migration'lar ortam değişkeninden bağımsız hep aynı
  DB'yi hedefliyordu (K8s/prod'da farklı bir DB'ye migrate etmenin yolu
  `alembic.ini`'yi elle değiştirmekti). `DATABASE_URL_SYNC` set edilmişse
  artık gerçekten kullanılıyor.
- Alembic tek head: `faz169` (faz161 + faz168 birleşimi). Bilinen borç #6
  tamamen kapandı.
- `pytest -q`: 340 passed, 1 skipped, 1 xpassed, **0 xfailed**.

### Kapsam dışı bırakılanlar (Faz 182'nin geri kalanı)
| # | Ne | Neden şimdi değil |
|---|----|--------------------|
| 20 | Stress/soak test, profiling + performans optimizasyonu. | Bu ortamda gerçek yük üretecek altyapı (çoklu eşzamanlı kullanıcı simülasyonu) yok; `qrp-api` image'ı da 11.6GB (torch/sentence-transformers ağırlıklı) — CPU-only torch wheel ile küçültülebilir, yapılmadı (bkz. `k8s/README.md`). |
| 21 | ~~Bağımsız güvenlik denetimi~~ **Kısmen kapandı:** yukarıdaki "Faz 182 — Güvenlik incelemesi" bölümüne bakın (6 aday bulgu, bağımsız doğrulama, hiçbiri yüksek güven eşiğini geçmedi). Gerçek bir üçüncü taraf/insan denetimi hâlâ değil — penetrasyon testi de yapılmadı. | P2 | Gerçek üçüncü taraf denetimi proje sahibinin kararı |
| 22 | ~~Dokümantasyonun otomatik doğrulanması~~ **Kapandı:** `scripts/check_docs_consistency.py` — CURRENT_STATE.md'deki `**Test:** N passed` satırını gerçek `pytest --collect-only` sayısıyla karşılaştırıyor, sapma >5 ise CI'ı kırıyor. `.github/workflows/ci.yml`'e eklendi. Yan bulgu: CI `alembic upgrade head` (tekil) kullanıyordu — migration zincirinde 2 head varken (bu oturumdan önce) bu komut CI'da hata verirdi; `heads` (çoğul) yapıldı, ayrıca `DATABASE_URL_SYNC` env var'ı eksikti (tesadüfen doğru varsayılana düşüyordu), eklendi. | — | — |

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

- ~~**Açık borç:** İki beyin yasağı — CognitiveEngine (stage zinciri) vs Orchestrator (RSI shortcut).~~
  **Güncel durum (2026-08-05):** Bu not artık yanıltıcı — `CognitiveOrchestrator.__init__`
  `self.engine = CognitiveEngine()` kuruyor, `run_cycle()` gerçek karar için
  doğrudan `self.engine.run(ctx, persist=False)`'a delege ediyor (rsi/ema/macd
  hesaplaması sadece `ctx.market.features`'ı doldurmak için bir veri-hazırlama
  adımı, rakip bir karar mantığı değil). İki bağımsız "beyin" yok; tek risk
  vardı ve gap #15'te bulunup kapandı: her iki giriş noktası da (`/cognitive/run`
  ve `run_cycle()`) `ctx.risk.limits`'i bağımsız olarak hiç doldurmuyordu.
