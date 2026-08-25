# Backlog — 2026-08-23 kullanıcı taraması

Kullanıcının "2 gün offline kaldım, sistemi gözlemleyip topladım" turunda getirdiği
16+ maddelik liste + harici bir mimari incelemenin (muhtemelen GPT) 8 maddelik
"confidence timeline" bulgusu. Hepsi tek seferde uygulanmadı — önce triyaj edildi,
gerçek kodla doğrulanabilenler doğrulandı. Sırayla işlenecek.

## ✅ Bu turda doğrulanıp düzeltildi

1. **Basis Arb, Dashboard'daki tür-dağılım kartlarında hiç görünmüyordu.**
   Kök neden: `dashboard/src/views/Dashboard.tsx::TRADE_TYPE_ORDER` sabit listesi
   `["scalp","swing","hedge","pump_fade"]` idi — Faz 344'te backend'e (`_classify_
   trade_type`) `basis_arb` eklenmişti ama bu listeye hiç eklenmemişti (pump_fade'in
   Faz 268-sonrası'ndaki AYNI hatasının tekrarı — o zaman da liste dışı kalan yeni
   tür sessizce kayboluyordu). 90 açık basis_arb pozisyonu etkilendi. **Düzeltildi**
   (`basis_arb` eklendi).
2. **"50 küsür pump-fade pozisyonu dashboard kartlarında var ama Transactions'ta
   filtrelediğimde 0 görüyorum."** Kök neden: `Transactions.tsx`'teki tür/yön/kâr-
   zarar filtresi SADECE o an sayfalanmış (limit=100) `open` state'i üzerinde
   çalışıyordu. pump_fade Ağustos 20'den beri yeni pozisyon açmadığı için (`pump_
   fade_enabled=false`) tüm pump-fade satırları en-yeni-önce sırada çok gerideydi
   (794 açık pozisyonda sıra 612-668) — sayfa 1'de hiç yoktu, filtre "doğru" şekilde
   sıfır gösteriyordu ama kullanıcı için yanlış görünüyordu. **Düzeltildi**: bir
   filtre aktifken sayfalama atlanıp tüm açık pozisyonlar (limit=5000) tek seferde
   çekiliyor.

## ✅ Faz 355'te düzeltildi

3. **[ÇÖZÜLDÜ — Faz 355] Confidence timeline parçalanmış (harici incelemenin #1/#2 maddesi — kodla
   bağımsız doğrulandı).** `MetaStage` (`cognitive_pipeline.py:235`) `ctx.decision.
   confidence`'ı belirliyor — ACT/WAIT eşiği VE Kelly boyutlandırma BU değeri
   kullanıyor. `DecisionFusion` (`decision_fusion.py:97`) bunu kalibre edilmiş
   FARKLI bir değerle EZİYOR. `orchestrator.py` (satır 971-972, 1012-1013) —
   `CognitiveEngine.run()` TAMAMEN bittikten SONRA, portföy ENB/korelasyon
   indirimiyle confidence'ı TEKRAR çarpıyor, ama act_threshold'u yeniden hiç
   kontrol etmiyor. Bugün canlı bir XAUTUSDT kararında bizzat gözlemlendi:
   `portfolio_confidence_discount` adımı confidence'ı 0.819→0.6833 düşürüyor —
   MetaStage'in ACT kararını verdiği eşik hâlâ eski (yüksek) değerdi. Aynı sorunun
   ikinci yarısı: eşik sonrası confidence düşse bile pozisyon zaten açılmış oluyor,
   boyut küçülüyor ama "bu karar gerçekten eşiği geçiyor muydu" sorusu bir daha
   sorulmuyor.
   **Çözüm (Faz 355):** iki indirim bloğu artık `final_size`'ı da aynı oranda
   küçültüyor, ve indirim sonrası confidence act_threshold'un altına düşerse
   karar dürüstçe WAIT'e çevriliyor. Not: bu SADECE portföy-seviyesi (orchestrator)
   yarısı — DecisionFusion'ın kendi kalibrasyonu zaten sağlamdı, dokunulmadı.

4. **[KISMEN ÇÖZÜLDÜ — Faz 358, fiyat-bazlı kısmı madde 23'e taşındı]** Aynı
   sembolde tekrar aynı yönde pozisyon açarken elindeki pozisyonun giriş
   fiyatı hiç kontrol edilmiyordu (kullanıcı örneği: $5→$7→$9 LONG
   piramitleme). Gerçek veriyle ölçüldü (bkz. madde 23): "kötü fiyattan
   piramitleme kazanma oranını düşürür" tezi net desteklenmedi, kullanıcı
   henüz ikna olmadı — o kısım AÇIK bırakıldı (madde 23). Ama kullanıcının
   kabul ettiği FARKLI, daha savunulabilir bir tez ("toplam maruziyeti
   sınırlamak kötü değil") Faz 358'de uygulandı: yeni `max_same_symbol_
   direction_capital_pct` ayarı (varsayılan %15, canlı veriyle kontrol
   edildi — mevcut hiçbir pozisyonu aniden bloklamıyor) — aynı sembol/yönde
   bağlı GERÇEK marjin kasanın bu yüzdesini geçerse yeni pozisyon reddedilir
   (`RiskGateStage`, `MAX_SAME_SYMBOL_DIRECTION_CAPITAL`). ENB/Cross-Symbol
   Correlation Filter'a YAMANMADI — o mekanizma denendi, YANLIŞ yönde sonuç
   verdiği doğrulandı (farklı sembollerin çeşitlendirmesini ölçüyor, tek
   sembolün kendi yığılmasını değil) — ayrı, doğrudan bir $-tavanı olarak
   uygulandı.

5. **[ÇÖZÜLDÜ — Faz 359, 2026-08-24] Kâr koruma / trailing yok — 10k kârdan
   başa-başa kadar bekliyor.** Kademeli kâr kilitleme (`progressive_lock_
   min_profit_r`/`progressive_lock_fraction`) uygulandı — bkz. madde 25.

## Madde 6-10 — 2026-08-24'te tek tek kodla doğrulandı

6. **[YANLIŞ ALARM — kapatıldı]** "REDUCE kararı recorder'da normal pozisyon
   açılışıyla aynı yolu izliyor, `küçült` niyeti `küçük aç` davranışına
   dönüşüyor olabilir" şüphesi doğrulanmadı. Kod incelendi:
   `contracts/contexts/decision.py::ActionType` içinde ayrı bir `EXIT`
   değeri var ama koda `grep`lendi — pipeline'da HİÇBİR YERDE
   kullanılmıyor (ölü). Sistemde "mevcut açık pozisyonu küçült/kırp"
   diye bir council-kararı yolu YOK — trimme sadece ayrı, açık uçlardan
   (`close_partial`, guardian sweep'leri) tetikleniyor. `ActionType.REDUCE`
   Faz 268g'den beri BİLEREK "düşük konviksiyonla KÜÇÜK aç" anlamına
   geliyor (`MetaStage`: `final_size = proposed_size * confidence`) —
   mevcut davranış tasarım gereği, bug değil.
7. **[GERÇEK, KARAR BEKLİYOR]** Agent-agreement sinyali GERÇEKTEN iki ayrı
   yoldan cezalandırılıyor: `DecisionFusion.evaluate()` agreement<0.34 ise
   confidence'ı ×0.6883 çarpıyor (Faz 328) — bu confidence hem ACT/WAIT
   eşiğini hem Kelly boyutlandırmayı etkiliyor. AYRICA `RiskTargetStage`
   (`engines/cognitive_pipeline.py`) AYNI `agent_agreement` sinyalini
   (aynı entropi formülü, `analytics/opportunity_quality.py`) bir ÖZELLİK
   olarak Meta-Label Model'e veriyor (Faz 351), o da KENDİ öğrenilmiş
   boyut çarpanını AYRICA uyguluyor. İki mekanizma da tek tek gerçek
   veriyle doğrulanıp wire edilmişti ama BİRBİRİNDEN BAĞIMSIZ tasarlandı
   — aynı düşük-agreement durumu şu an iki kez küçültülüyor olabilir.
   **Karar gerekiyor**: kasıtlı katmanlı temkinlilik olarak mı bırakılsın,
   yoksa biri kaldırılıp/zayıflatılıp mı tek kanala indirilsin? İkisini
   birlikte vs ayrı ayrı çalıştırmanın gerçek kalibrasyon etkisini ölçmek
   gerekiyor.
8. **[ÇÖZÜLDÜ, 2026-08-24]** `services/cognitive_engine.py::_persist_and_
   learn` yorumu hâlâ Faz 284'te ("karar mekanizmasına hiç katkısı yoktu")
   TAMAMEN kaldırılmış `backtest/real_historical_backtest.py`'den ikinci
   bir öğrenme kaynağıymış gibi bahsediyordu — doğrulandı (dosya gerçekten
   yok, sadece stale .pyc kalıntısı) ve yorum güncellendi: gerçek öğrenme
   artık SADECE `position_closer.py` (gerçek kapanışlar) üzerinden.
9. **[ÇÖZÜLDÜ, 2026-08-24]** `version.py::SYSTEM_VERSION` (1.53.0)
   `CURRENT_STATE.md`'nin (v1.99.0) 46 versiyon gerisindeydi — Faz 348
   şemayı birleştirmişti ama sonraki hiçbir faz'da elle senkronlanmamış.
   1.99.0'a güncellendi (hâlâ elle senkron — otomatik değil, bir sonraki
   turda tekrar geriye düşebilir).
10. **[ÇÖZÜLDÜ, 2026-08-24]** `engines/cognitive_pipeline.py`'deki
    strong-dissent açıklama yorumu hâlâ eski 0.75/0.90 rakamlarından
    bahsediyordu — gerçek sabitler (`STRONG_DISSENT_CONFIDENCE_THRESHOLD
    =0.65`, `BENCHED_..._THRESHOLD=0.70`, dosyanın KENDİ tanım yorumunda
    zaten doğru yazılıydı) ile çelişiyordu. Güncellendi.

## 🆕 Yeni özellik/analiz istekleri (henüz kod incelemesi gerekmiyor, tasarım kararı gerekiyor)

12. **[ÇÖZÜLDÜ — Faz 356] Kazanma oranı çöküşü (21-23 Ağustos, ~%85 → %38)
    için otomatik rejim-değişimi tespiti.** `scientific_self_correction.py`
    canlıya bağlandı (Genel Özet paneli, 14. modül). Gerçek bulgu: genel
    isabet düşmemiş (%70→%79, iyileşmiş), ama **LONG özelinde gerçek/anlamlı
    bir bozulma var** (%96.2→%80.6, p<0.0001). SHORT ve deney kovaları
    (control/treatment) değişmemiş. Kullanıcının sezgisi kısmen doğru
    çıktı — sistem genelinde değil, sadece LONG'da.
13. **Portföy-seviyeli "triyaj" mantığı**: "100 pump_fade pozisyonum var, 70'i
    +20k kârda, 30'u riskli — kötüye giderse -50k olabilir, şimdi hepsini kapatıp
    +2k'da kalmak -50k'dan iyidir" tarzı senaryo-bazlı karar. Şu an sistemde
    böyle bir mekanizma yok — `analytics/stress_testing.py` (yine bugün bulunan,
    wire edilmemiş) buna yakın bir temel sağlayabilir (gerçek geçmiş en-kötü-N-
    dönem senaryosunu mevcut pozisyona uygulama).
14. **Otomatik, sürekli çalışan "stop kök-neden" analiz motoru** (kullanıcı
    örneği: "BTC LONG'da 100 pozisyon, 15'i stop olmuş, 13'ü yön hatası, 2'si
    stop süpürülüp sonra hedefe gitmiş"). Yeni bir analytics modülü + periyodik
    Celery görevi gerektirir — henüz hiçbir yerde yok, sıfırdan tasarım.
15. Ayrıca kâr edip zarara dönen ("breakeven'dan çıkış") pozisyonların ne kadarının
    stop yanlış yerleştirildiği için mi, yoksa gerçekten yön hatası mı olduğu
    araştırılmalı; bu kaybın toplam zarardaki payı % olarak dashboard'a kart
    olarak eklenmeli (SL/likidasyon/breakeven kırılımı).
16. **[ÇÖZÜLDÜ — 2026-08-24, A/B'den ÜRETİME terfi ettirildi] Settings'teki
    mum aralığı (candle timeframe) tek seçime zorluyor mu?** `candle_
    timeframe` (tekil) ÖLÜ DEĞİL — birincil karar zaman dilimi. "15dk/4s
    ayrı ayrı değerlendiriliyor mu" sorusu: Multi-Timeframe Cascade
    (Faz 268c, `propose_multi_timeframe()`) zaten var VE gerçekten
    çalışıyormuş — ilk kontrolüm (5000 satırlık yanlış alanda arama)
    hatalıydı, düzeltilmiş sorguda **79.028 karar** bulundu (13-24
    Ağustos, kesintisiz). Gerçek `services/ab_testing.py::evaluate_
    experiment` ile ölçüldü (n=1117 control / 1094 treatment kapanmış
    işlem): agrega fark anlamsız (p=0.63) ama yön kırılımında SHORT win
    rate'i %8.5'ten %21.9'a çıkarıyor (p=0.00008, çok anlamlı), LONG'da
    anlamlı zarar yok (p=0.69). Maliyet: sembol başına ~3x CognitiveEngine
    (yerel CPU, LLM API'sine dokunmuyor) + 2 ek Binance REST isteği/
    sembol/cycle. Kullanıcı kararı (CPU maliyeti M5'te sorun değil, rate-
    limit'te %50 trafikte sorun görülmedi): deney sonlandırıldı, ÜRETİME
    terfi ettirildi — `multi_timeframe_cascade_ab_test_enabled=false`,
    `multi_timeframe_cascade_enabled=true` (app_settings'te canlı
    olarak değiştirildi, restart gerekmiyor, bir sonraki cycle'dan
    itibaren TÜM sembollerde aktif).
17. **"Tepeden giriş" hâlâ devam ediyor** (bugünkü XAUTUSDT örneği zaten
    incelendi — ADX zayıfken bile hiçbir sert engel yok). Kullanıcı özellikle
    destek/direnç seviyesi bazlı bir filtre istiyor: kritik seviyeden %X'ten
    fazla uzaktaysa (örn. tepeden/dipten kovalıyorsa) giriş engellensin.
18. Genel: sistem "her fırsatı alıyor," seçicilik eksik — giriş eşiği/kriterleri
    gözden geçirilmeli.
19. **[ÇÖZÜLDÜ — 2026-08-24, TAM olarak] "Pozisyon büyütme asla" ilkesi
    dokümante edildi, TÜM çarpanlar doğrulandı VE bulunan tek istisna
    kapatıldı.** `docs/index.md`'ye "Temel Prensipler"e eklendi.
    Doğrulananlar: `kelly_size_multiplier`, `meta_label_size_multiplier`,
    `drawdown_size_multiplier`, `InnerCritic.confidence_multiplier`,
    pump_fade'in iki yoğunluk/rejim çarpanı, `pyramid_dampened_leverage`,
    `max_safe_leverage`. **Bulunan istisna kapatıldı:** `services/agent_
    confidence_model.py::predict_confidence_multiplier`'ın üst sınırı
    (`MULTIPLIER_MAX`) `1.5`'ten `1.0`'a çekildi — kullanıcı kararı:
    "ilkenin ruhuna açılan teorik gediği hemen kapatalım, Kelly
    boyutlandırma kontrolden çıkmasın." Artık ajan-güveni katmanı da
    dahil TÜM çarpanlar istisnasız SADECE küçültebiliyor. 2 test
    güncellendi (`test_agent_confidence_model.py`, `test_council_
    orchestrator.py` — yukarı-yönlü senaryolar aşağı-yönlü senaryolara
    çevrildi, ilgili regresyon temiz).
20. Arbitraj pozisyon detay kartı istek listesi: spot/futures bacak, entry/current
    basis, funding earned, fees, unrealized/net PnL, exit condition — Dashboard'a
    yeni bir detay görünümü.
21. **[YAPILDI — kod hazır, COMMIT/WIRE EDİLMEDİ, 2026-08-24] Dashboard'a
    "AI şu an piyasa yönünü nasıl görüyor" bilgi kartı.** `DecisionPersistor.
    latest_direction_confidence_by_symbol()` (DISTINCT ON, tek sorgu, son
    24 saatte taranmış her sembolün EN SON yön/confidence'ı) + yeni `GET
    /dashboard/market-direction-summary` + Dashboard.tsx'e yeni kart
    (LONG/SHORT/WAIT yüzdeleri, ortalama güven, en güvenli 5 LONG/SHORT
    sembol). 2 yeni backend test + tsc temiz. Kullanıcı dönene kadar
    commit edilmedi (talimatı gereği).
22. **Pump-fade'de nadir/aşırı fırsatları (token 2x+ yapmış vb. "absürt"
    hareketler) yakalayabilme.** Kullanıcı isteği (2026-08-24): şu anki
    pump_fade eşikleri (min_gain_pct vb.) muhtemelen bu tür nadir, büyük
    fırsatları normal aralığın dışında bıraktığı için hiç görmüyor —
    bunları nasıl yakalayabileceğimiz üzerine ayrı bir araştırma/tasarım
    turu gerekiyor. Henüz kod incelemesi yapılmadı, en sona bırakıldı.
    **Birleştirildi (2026-08-24):** `pump_fade_lookback_hours` (şu an
    varsayılan 48s) — 24s/72s/1 hafta gibi farklı pencereler daha mı iyi
    performans gösterir? Kontrol edildi: yerel DB'de ham mum (OHLCV)
    geçmişi YOK (`candles`/`ohlcv` tablosu yok, `ingest_candles_task`
    hiç kalıcı yazmıyor) — bu yüzden bunu ölçmek için Binance'in genel
    API'sinden GERÇEK geçmiş mumları taze çekip `find_pump_candidates`'i
    farklı `lookback_hours` değerleriyle yeniden çalıştıran bir mini-
    backtest kurmak gerekiyor. İkisi de `find_pump_candidates` mantığına
    dokunduğu için AYNI turda ele alınacak — henüz başlanmadı.
23. **[ÇÖZÜLDÜ — Faz 361, 2026-08-24] Aynı sembolde kötü fiyattan
    piramitleme (madde 4'ün devamı).** İlk basit test (kötü/iyi fiyat,
    rejim ayrımı yapmadan) anlamlı fark göstermemişti — kullanıcı ikna
    olmadı, açık bıraktı. Rejime göre (`market_regime = "{trend}_
    {volatility}"`) kırılınca gerçek tablo ortaya çıktı (3826 AI-only
    kapanmış karar): SADECE "bullish_low" rejiminde worse-price add
    gerçekten avantajlı (n=355, %76 — fresh giriş %63'ten bile yüksek).
    Diğer TÜM rejimlerde (bullish_normal %53, bullish_high %44,
    bearish_low %42, bearish_normal %35, bearish_high %28, unknown %30)
    fresh girişten kötü ya da en kötü seçenek. 22-24 Ağustos zayıflık
    penceresinde günlük kırılım daha da netti: worse-price add win_rate
    %77→%38→%9 (better-price add ve fresh girişten hep daha kötü).
    Kullanıcı kararı: "sadece en yüksek performans gösterdiği rejimde
    izin verelim, onun dışında kesin olarak yasaklayalım." Uygulandı:
    `analytics/pyramid_regime_gate.py::is_worse_price_pyramid_blocked()`
    (saf fonksiyon) + `services/decision_recorder.py`'ye wire edildi
    (entry_price hesaplandıktan hemen sonra, Position Pool kontrolüyle
    AYNI yer) + `DecisionPersistor.avg_open_entry_price_by_symbol_
    direction()`. Ayarlar: `pyramid_regime_gate_enabled` (varsayılan
    true, koruyucu mekanizma), `pyramid_worse_price_allowed_regime`
    (varsayılan "bullish_low"). Fail-closed: rejim unknown/None ise
    engellenir. **Bilinen sınır:** Position Pool (madde altındaki Faz
    350, varsayılan kapalı) yoluyla açılan adaylar bu kapıdan GEÇMİYOR
    — `resolve_due_pool_windows()` council market context'ine (dolayısıyla
    rejime) sahip değil, ayrı bir iş gerektirir, düşük öncelik (havuz
    zaten kapalı).

24. **[YAPILDI — kod hazır, COMMIT EDİLMEDİ, 2026-08-24] Transactions
    sayfasındaki kapalı işlemler tablosu 100 kayıtla sınırlıydı.**
    `list_closed_trades()`/`GET /trades`'e `offset` eklendi (`list_open_
    positions`'ın Faz 268y'deki AYNI deseni). Frontend: `TRADES_PAGE_SIZE`
    + `tradesPage` state, açık pozisyonlarla AYNI "← Önceki / Sonraki →"
    sayfalama kontrolleri. 1 yeni backend testi + tsc temiz. Kullanıcı
    dönene kadar commit edilmedi.

25. **[KISMEN ÇÖZÜLDÜ — Faz 359, (b) madde 26'ya taşındı] "Başabaş çekildi"
    etiketi yanıltıcı — gerçek veriyle doğrulandı, 2026-08-24.** Kullanıcı
    gerçek örnekler gösterdi: LTCUSDT scalp LONG
    "Başabaş çekildi" ama pnl -$140.22, -$119.64, -$92.99, -$66.01 vb.
    Kod incelendi (`services/position_closer.py::_apply_breakeven_stop` +
    `close_due_positions`): MEKANİZMA gerçekten çalışıyor — stop
    girişe(entry_price'a) doğru çekiliyor (gerçek örnek: entry=52.3747,
    stop=52.3747, tam girişte). Ama İKİ ayrı gerçek sorun var:
    (1) **Gerçek slippage/gap**: exit_price = periyodik kontrol anındaki
    current_price (stop fiyatının KENDİSİ değil) — fiyat, çekilmiş stopu
    check aralığında (60sn) atlayabiliyor. Aynı örnekte exit=52.09,
    stop=52.3747 — %0.55 gap, ~$115 gerçek fiyat kaynaklı zarar (Faz313'te
    KAIAUSDT'de zaten tespit edilmiş AYNI mekanizma, o zamandan beri
    mitigasyon eklenmemiş).
    (2) **Yanıltıcı eşik**: `_BREAKEVEN_LOSS_REDUCTION_THRESHOLD=0.5` —
    "breakeven_stop" etiketi gerçek zarar ORİJİNAL (geniş) stop mesafesinin
    YARISINDAN küçükse veriliyor, ~$0'a yakın olduğu için DEĞİL. Yani
    orijinal stop $950 kaybettirecekken $140 kaybetmek "başabaş" sayılıyor
    — matematiksel olarak "tam zarardan iyi" ama kullanıcı dilinde
    "başabaş" değil. Olası çözümler (tartışılacak): (a) dashboard
    etiketini "Kısmi Zarar Önlendi" gibi daha dürüst bir isme çevirmek,
    (b) check aralığını sıklaştırmak (gerçek gap'i azaltır), (c) eşiği
    sıkılaştırmak. **Faz 359'da (b) ve (c) hariç, (a)+kademeli kâr
    kilitleme uygulandı** — check aralığı sıklaştırma AYRI, madde 26'ya
    taşındı (rate-limit nedeniyle basit REST polling ile güvenli değil).

26. **[ÇÖZÜLDÜ — Faz 360, 2026-08-24] Pozisyon kapatma için "anlık" fiyat
    taraması (kayma azaltma).** Kullanıcı onayıyla uygulandı:
    `services/realtime_position_monitor.py` — Binance trade WebSocket'ine
    (geçerli sembol filtresi `exchangeInfo` ile, ~30dk'da bir tazelenir)
    abone olup her tick'te `PositionCloser._process_position_at_price()`'ı
    (REST periyodik tarama ile AYNI, paylaşılan mantık) çalıştırıyor.
    REST periyodik tarama (`close_due_positions_task`, 60sn) KALDIRILMADI
    — WS koparsa/gecikirse arkadaki güvenlik ağı. `DecisionPersistor.
    close_position()`'a `WHERE status='open'` yarış-koruması eklendi (iki
    yol aynı pozisyonu eşzamanlı görebiliyor artık). Kalıcı süreç olarak
    çalışıyor, `scripts/service_watchdog.sh`'a eklendi (düşerse otomatik
    yeniden başlar). Canlı doğrulandı: gerçek bir stop-tetiklenmiş
    pozisyonu (VIRTUALUSDT) doğru kapattı.

27. **[ÇÖZÜLDÜ — Faz 360-361, 2026-08-24] Scalp LONG isabet oranındaki
    düşüş (%95 → %83) araştırıldı.** Doğru metodolojiyle (manual_full/
    manual_partial hariç, gerçek AI kararları) günlük kırılım: 19-21
    Ağustos %87-100 (kullanıcının hatırladığı iyi dönem), 22 Ağustos'ta
    çöküş (%18), 23-24'te devam eden zayıflık (%48, %15). İki ayrı kök
    neden bulundu: (1) 22 Ağustos sabahı GERÇEK bir altyapı kesintisi
    (`risk_limits.max_position_size` eksikti, saatlerce ~14.000 ardışık
    fail-closed WAIT — ajanlara hiç sorulmadan, aynı gün Faz 350'de
    bulunup düzeltildi). (2) 23-24 Ağustos'taki devam eden zayıflık
    piramitleme ile ilişkili çıktı — bkz. madde 23, Faz 361'de rejim-
    bazlı kapı ile ele alındı.

## 🆕 Yeni bulgular (henüz ölçülmedi)

28. **SHORT swing isabet oranı çarpıcı derecede düşük.** Kullanıcı bulgusu
    (2026-08-24, muhtemelen bir dashboard/research panelinden):
    `ai_council_SHORT_swing` genel isabet %9.0 (n=465) vs `ai_council_
    LONG_swing` %91.5 (n=823). Faz 342'nin zaten bulup gate'lediği
    "SHORT + bearish + low volatility" kombinasyonuyla (n=424, %8.3)
    çakışıyor olabilir — swing SHORT popülasyonunun çoğu o rejimde
    birikmiş olabilir. Doğrulanması gerekiyor: madde 28'i madde 23'teki
    gibi rejime göre kırıp, gerçekten SADECE bearish_low mu yoksa SHORT
    swing'in TÜMÜ mü sorunlu olduğunu ayırt etmek lazım — henüz ölçülmedi.

29. **[SONA ERTELENDİ, KULLANICI ONAYIYLA] Eşzamanlı açık pozisyon sayısı
    (test modu ~2.000 vs canlı hedef 5-10) ile kazanma oranı korelasyonu.**
    Kullanıcı sorusu (2026-08-24): test modunda çok fazla eşzamanlı işlem
    açık kalması sistemi olduğundan başarılı gösteriyor olabilir mi?
    Ölçüldü (5194 kapanmış karar, interval-overlap sorgusu): olgun dönemde
    (8 Ağustos sonrası) eşzamanlı pozisyon sayısı HİÇBİR ZAMAN 255'in
    altına inmemiş — sistemin gerçekten 5-10 pozisyonla çalıştığı hiçbir
    dönem yok, bu soruyu geçmiş veriyle cevaplamak mümkün değil. En yakın
    mevcut altyapı: Faz 350'nin Position Pool/Max Confidence Modu (top-K
    seçim, varsayılan kapalı) — kontrollü açılıp gerçek ölçüm yapılabilir.
    Kullanıcı isteğiyle şimdilik ertelendi, todo'nun sonunda kalıyor.

30. **Basis Arb: %75 kazanma oranı ama toplam PNL eksi.** Kullanıcı bulgusu
    (2026-08-24): 8 kapanmış işlem, 6 kazanan/2 kaybeden, ama toplam
    -$88.66. DB'den çekildi: STORJUSDT ve SCRTUSDT'nin SHORT bacakları
    TAM AYNI tutarda (-$98.05, -$98.05 — şüpheli derecede özdeş) `reason=
    liquidation` ile likide olmuş; karşılık gelen LONG bacakları
    (muhtemelen spot/hedge tarafı) sorunsuz, ılımlı kârla (+$60.79,
    +$42.74) `manual_full` ile kapanmış. Yani hedge'in SHORT/perp
    tarafı, basis spread'i yakalamadan ÖNCE likide oluyor — muhtemelen
    o bacağın kaldıraç/teminat boyutlandırması spread'in beklenen
    büyüklüğüne göre çok dar. Kök neden henüz `services/basis_
    arbitrage_strategy.py`'de incelenmedi — iki liquidation tutarının
    özdeş olması (rastgele değil, sabit bir teminat/boyut formülüne
    işaret ediyor) ilk bakılacak yer. Henüz ölçülmedi/kod incelemesi
    yapılmadı.

31. **[ÇÖZÜLDÜ — Faz 362/362-devam, 2026-08-24] "Council'in fikir değiştirmesi"
    verisi — hem çıkış hem giriş tarafı ölçüldü, İKİSİ DE canlıya alındı.**
    Kullanıcı sorusu: kullanılmayan `ActionType.EXIT`'in gerçek bir
    kapasite eksikliğine (proaktif, inanç-değişimi-tetiklemeli çıkış)
    işaret ettiği bulundu. Çıkış tarafı İLK ÖLÇÜMDE (dar, 4 günlük, n<=27)
    REDDEDİLMİŞTİ — kullanıcı "küçük örneklem sorunu olabilir" diye
    sorguladı ve HAKLI ÇIKTI: aynı geniş pencerede (10-24 Ağustos, 3619
    pozisyon) tablo TAMAMEN değişti — N=6 ardışık onaylı (confidence>=0.65)
    tersine dönüşte %89 "daha iyi olurdu" (n=187, toplam +$480), N<=4'teki
    felaket boyutlu uç değerler (-$800'e varan) tamamen kayboluyor. Canlıya
    alındı: `services/belief_reversal_exit.py` + `belief_reversal_exit_task`
    (60sn, `regime_reversal_guardian` ile AYNI mimari) — ayarlar:
    `belief_reversal_exit_min_consistent_cycles=6`, `belief_reversal_exit_
    min_confidence=0.65`, varsayılan açık. Giriş tarafı ("aynı gürültü
    yeni pozisyonlara da mı giriyor?") ÖLÇÜLDÜ VE DOĞRULANDI:
    3619 pozisyonda run=0-3 (taze/az tutarlı sinyal) TEK TEK ortalama
    zarar ediyordu, run=4'te ilk net pozitif. Toplam-kâr-maksimize eden
    eşik bağımsız ölçümle AYNI N=4'e işaret etti ($116,335 tepe). Canlıya
    alındı: `analytics/signal_persistence.py` + `services/decision_
    recorder.py` (ayar: `signal_persistence_min_consistent_cycles=4`,
    varsayılan açık). Sürekli yeniden ölçüm için `services/signal_
    persistence_gatherer.py` Genel Özet paneline bağlandı — optimum N
    veri büyüdükçe otomatik gösterilir (ama canlı ayarı otomatik
    DEĞİŞTİRMEZ, kullanıcı elle günceller).

32. **[ÇÖZÜLDÜ — 2026-08-24] Ölü RL-ödül-şekillendirme kalıntısı temizlendi.**
    `ActionType.EXIT`'i ararken bulunan `services/opportunity_cost.py`
    (`OpportunityCostCalculator`) — kullanıcı "Opportunity Quality" (Faz
    328/351, CANLI) ile karıştırdığını fark etti, ikisi TAMAMEN farklı
    modüller. Kod arkeolojisi: `opportunity_cost.py`/`outcome_evaluator.py`/
    `reward_signal.py` üçü de projenin `Faz 1`'den ÖNCEKİ ilk "Initial
    checkpoint" commit'inin parçası — hiçbiri hiçbir "Faz N" kararıyla
    bilerek eklenmedi, hiçbiri gerçek `CognitiveEngine.run()` akışına hiç
    bağlanmadı (Faz 250/268j'nin "sahte ForwardOutcome ile kirletmeyelim"
    kararıyla AYNI aile — sadece silinmesi unutulmuş). Kullanıcı onayıyla
    silindi: 3 servis dosyası + `contracts/opportunity.py` (`OpportunityCost`)
    + `FailureType` (contracts/outcome.py'den) + 3 test dosyası, `contracts/
    __init__.py`/`services/cognitive_engine.py`'deki ölü referanslar
    temizlendi. `TradeOutcome`/`DecisionEvaluation` BİLEREK KORUNDU — hâlâ
    6+ regresyon testinin ("bu alan set edilse bile öğrenme tetiklenmiyor")
    gerçekten kullandığı bir tip. 72 test (ilgili tüm dosyalar) temiz.

    **Ayrıca bulundu, DOKUNULMADI (kapsam dışı, kullanıcı onayı gerekir):**
    `services/belief_updater.py` (`BeliefUpdater` — sıfır çağıranı var,
    `DecisionEvaluation` kullanıyor ama hiçbir yerden tetiklenmiyor) ve
    `rl/incremental_learning/loop.py` (kendi bağımsız `TradeOutcome`
    tanımı var, `contracts/outcome.py`'den TAMAMEN bağımsız, sıfır
    çağıranı var — muhtemelen ayrı, daha eski bir RL taslağı). İkisi de
    ayrı bir onay/tur gerektirir.

33. **Telegram üzerinden push bildirimi.** Kullanıcı isteği (2026-08-25):
    mevcut sistem sessizlik/duruş alarmı tarayıcı sekmesi açıkken çalışıyor
    (ses + masaüstü bildirimi + banner, bkz. observability/signal_health.py
    + Dashboard.tsx). Bilgisayar kapalıyken/tarayıcı kapalıyken ulaşmıyor —
    kullanıcı şimdilik bunu yeterli buluyor (test modu), ama Telegram gibi
    harici bir push kanalı (bot token + chat id kurulumu gerektirir) ileride
    istenirse ayrı bir tasarım turu olarak ele alınacak. Şimdilik SADECE not.

34. **[YAPILDI — Faz 363, 2026-08-25] Settings'e sabit $ pozisyon
    boyutlandırma alanı.** Kullanıcı isteği: değişken boyutlu pozisyonlardan
    gelen PNL dalgalanmasını azaltmak ("%86 isabet oranı yakalıyor ama 2k
    dolar zarar ediyor"). `fixed_position_size_usd` ayarı (varsayılan "0" =
    kapalı) — pozitif değer girilirse dinamik `starting_capital*
    max_capital_pct/max_concurrent_positions` formülünün YERİNE geçip HER
    pozisyonu (sembol/yönden bağımsız) aynı $ notional'a sabitliyor.
    `services/orchestrator.py::_build_context` + `services/risk_state.py` +
    Settings.tsx'e yeni kart. 3 yeni test.

## Notlar

- Kullanıcı `max_open_positions_per_symbol_direction`'a (1000) bilerek
  dokunmamamızı istedi — test modunda gereksiz kısıtlama. Madde 4 (fiyat bazlı
  kontrol) bundan AYRI, hâlâ geçerli bir istek.
- Faz 353 (`moe_regime_router`) bu turdan önce zaten wire edildi ve commit
  edildi — ayrı.
