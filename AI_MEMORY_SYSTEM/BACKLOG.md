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
7. **[ÇÖZÜLDÜ — Faz 363, 2026-08-25] Agent-agreement "iki kez cezalandırma"
   şüphesi incelendi — teknik olarak doğrulanmadı, ama incelemeden DAHA
   CİDDİ bir bulgu çıktı.** `DecisionFusion`'daki opportunity-quality
   indirimi final_size'ı kademeli küçültmüyor (sadece EV kapısı: geçer/
   geçmez) — gerçek kademeli küçültmeyi SADECE Meta-Label Model yapıyor,
   "iki kez küçültme" yok. AMA: RiskTargetStage'in Meta-Label Model'e
   verdiği "confidence" özelliği DecisionFusion'dan ÖNCE hesaplanıyordu
   (ham, kalibrasyonsuz) — modelin EĞİTİM verisi ise decisions.confidence
   (DecisionFusion SONRASI, kalibre edilmiş) idi. Train/serve tutarsızlığı.
   Kanıt: agent_agreement'ın öğrenilmiş katsayısı beklenenin TERSİ yönde
   (-0.24) çıkmıştı. Düzeltme: `services/decision_fusion.py::
   compute_fused_confidence()` (yan etkisiz, ortak fonksiyon) — RiskTargetStage
   artık DecisionFusion'ın üreteceği NİHAİ confidence'ı kullanıyor.
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
13. **[YAPILDI — Faz 364, 2026-08-26] Portöy-seviyeli "triyaj" mantığı.**
    `analytics/stress_testing.py` (o gün bulunan, wire edilmemiş
    `compute_worst_historical_drawdown`/`apply_stress_scenario_to_notional`)
    yeni `services/portfolio_stress_guardian.py` ile bağlandı: MEVCUT TÜM
    açık pozisyonların toplam notional'ına (yön bazlı LONG/SHORT), referans
    sembolün (varsayılan BTCUSDT) gerçek tarihindeki en kötü N-günlük
    (varsayılan 7) DÜŞÜŞ (LONG kitabı) ve YÜKSELİŞ (SHORT kitabı, negatize
    edilmiş getirilerle AYNI fonksiyon) ayrı ayrı uygulanır (ikisi aynı anda
    olamayacağı için toplanmaz, daha kötüsü alınır). Şu an net kârdaysak AMA
    senaryo net zarara çevirecekse TÜM açık pozisyonlar (yön/strateji fark
    etmeksizin — Regime Reversal Guardian'ın aksine sadece kârdakiler değil,
    sistemik bir müdahale) `close_partial` ile kapatılır. Varsayılan AÇIK
    (Regime Reversal Guardian ile aynı gerekçe — koruyucu, alfa üretmiyor).
    Yeni Celery görevi (5dk'da bir, `_CycleLock` korumalı). 4 test.
14. **[YAPILDI — Faz 364, 2026-08-26] Sembol×yön stop kök-neden kırılımı.**
    Kullanıcı örneği: "BTC LONG'da 100 pozisyon, 15'i stop olmuş, 13'ü yön
    hatası, 2'si stop süpürülüp sonra hedefe gitmiş." Sıfırdan yeni bir motor
    yerine — `analytics/failure_classifier.py::summarize_loss_breakdown()`
    (madde 15, dün yapıldı) zaten AYNI sınıflandırmayı (gerçek MAE/MFE,
    direction_error/barrier_error) genel toplamda yapıyordu. Yeni
    `summarize_loss_breakdown_by_symbol_direction()` AYNI sınıflandırmayı
    (symbol, direction) hücrelerine böler (min_trades=5 altındaki hücreler
    gürültü olarak dışlanır, pump_fade_v1 hariç). Genel Özet panelinin
    (`services/research_summary_gatherer.py`) 17. modülü olarak eklendi —
    yeni bir dashboard sayfası GEREKMEDİ, mevcut jenerik panel deseni
    otomatik gösteriyor. 4 test.
15. **[ÇÖZÜLDÜ — Faz 363, 2026-08-25] Kâr edip zarara dönen pozisyonların
    stop yanlış yerleşimi mi yoksa gerçek yön hatası mı olduğu + zararın
    toplam paydaki oranı.** `analytics/failure_classifier.py::
    summarize_loss_breakdown()` (mevcut summarize_stop_loss_failures'ın
    TÜM zarar-üreten exit_reason'lara genişletilmiş hali) + Genel Özet
    panelinde yeni kart ("Zarar Kırılımı"). Gerçek sonuç: toplam zararın
    %88.8'i stop_loss'tan, bunun %96.6'sı gerçek yön hatası — "stop çok
    darmış" payı sadece %3.4. Kayıpların ezici çoğunluğu yerleşimden
    değil, yön tahmininden kaynaklanıyor.
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
17. **[YAPILDI — Faz 366-devam, 2026-08-27] "Tepeden giriş" — destek/
    direnç seviyesi bazlı filtre, gate CANLIDA.** Kullanıcı isteği:
    kritik seviyeden %X'ten fazla uzaktaysa giriş engellensin. Gerçek
    veriyle (450+ karar) kalibre edildi, makro seviye tanımı günlük
    klasik pivot noktaları (`compute_pivot_points`, koddaydı ama hiç
    kullanılmıyordu). Büyük-cap (`crypto_cap_tier()`, 16 sembol) ve
    küçük-cap AYRI test edildi — kullanıcının "her sembolde aynı
    çalışmayabilir" uyarısı doğru çıktı: large-cap'te temiz/monotonik
    desen (mesafe ≤%0.52'de win %95-98, %0.65'te %91.1, %2.20'de %84.4
    — eşik **~%0.6**), small-cap'te desen YOK/TERS (en yakın grup en
    kötü) — gate SADECE large-cap'e uygulanıyor.
    **İnşa edildi**: `analytics/pivot_distance_gate.py` (saf) +
    `services/orchestrator.py`'de zaten fetch edilmiş `daily_data`'dan
    (ekstra ağ isteği YOK) `nearest_pivot_distance_pct` hesaplanıp
    `ctx.market.features`'a yazılıyor + `decision_recorder.py`'ye wire
    (pyramid_regime_gate ile aynı noktada, entry_price hesaplanır
    hesaplanmaz). Yeni ayarlar: `pivot_distance_gate_enabled` (true),
    `pivot_distance_gate_threshold_pct` (0.006). Gerçek canlı BTC
    verisiyle uçtan uca doğrulandı (şu an mesafe %0.08, eşiğin altında,
    engellenmiyor). 24 test. uvicorn+celery worker+beat yeniden
    başlatıldı, temiz.
18. **[ÇÖZÜLDÜ — Faz 363, 2026-08-25/26] "Seçicilik eksik" incelendi —
    bkz. madde 36 (pump_fade izolasyonu) ve confidence=0.5 kovası kök neden
    analizi. Sonuç: yapısal bir seçicilik sorunu değil, geçmişte biriken
    kirlilik/tek seferlik olayların izi.
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
20. **[GEÇERSİZ — Basis Arb Faz 364'te (madde 46) tamamen kaldırıldı]**
    Arbitraj pozisyon detay kartı istek listesi: spot/futures bacak,
    entry/current basis, funding earned, fees, unrealized/net PnL, exit
    condition — Dashboard'a yeni bir detay görünümü. Strateji artık
    mimaride yok, madde konusu ortadan kalktı.
21. **[YAPILDI, COMMIT EDİLDİ] Dashboard'a "AI şu an piyasa yönünü nasıl
    görüyor" bilgi kartı.** `DecisionPersistor.latest_direction_confidence_
    by_symbol()` (DISTINCT ON, tek sorgu) + `GET /dashboard/market-
    direction-summary` + Dashboard.tsx kartı — canlı kodda doğrulandı
    (2026-08-26), 2026-08-24'teki "commit edilmedi" notu artık geçersiz.
22. **[YAPILDI — Faz 364, madde 47] Pump-fade'de nadir/aşırı fırsatları
    yakalayabilme.** Kullanıcı sorusu tam olarak Staged Entry'nin
    kalibrasyon turunda cevaplandı: 43 sembol/250 gün taraması, entry'den
    sonra fiyat medyan +%36/p90 +%82 daha yükseliyor ama örneklemde HİÇ
    +%90'a ulaşmıyor. `pump_fade_lookback_hours` alt-sorusu da AYNI turda
    çözüldü — Binance'ten taze geçmiş mumlarla mini-backtest kuruldu
    (yerel OHLCV geçmişi olmadığı için).
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
    sayfalama kontrolleri. 1 yeni backend testi + tsc temiz. Canlı kodda
    doğrulandı (2026-08-26) — commit edilmiş, eski not geçersiz.

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

28. **[ÇÖZÜLDÜ — madde 43'te detaylı] SHORT swing isabet oranı çarpıcı
    derecede düşük.** Kullanıcı bulgusu (2026-08-24): `ai_council_
    SHORT_swing` genel isabet %9.0 (n=465). Rejime kırılınca: %88'i
    (409/465) `bearish_low`'da (win_rate %5.4) — Faz 342'nin zaten
    gate'lediği "SHORT + bearish + low volatility" havuzuyla (n=424,
    %8.3) AYNI popülasyon, yeni bir sorun değil. Kalan `bearish_normal`
    (n=35) %34.3 — daha iyi, izlemede kalsın.

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

30. **[ÇÖZÜLDÜ — Faz 363, 2026-08-26] Basis Arb: kazanan
    işlem var ama likidasyon oranı %21+, 108 açık pozisyon var.** Kullanıcı
    sorusu ("buranın sisteme faydası nedir?") üzerine derinleşildi. Gerçek
    veri (2026-08-26): 14 kapanmış işlem, toplam -$177.67, win_rate %64.3
    ama 3/14 (%21.4) likidasyonla kapanmış. SCRTUSDT'de HEM LONG HEM SHORT
    bacağı likide olmuş (önceki turda sadece SHORT sanılıyordu) — tutarlar
    şüpheli derecede özdeş (-$97.95/-$98.05/-$98.05), hepsi ~%19.5 mesafede
    (5x kaldıraçla standart likidasyon marjı).

    KÖK NEDEN BULUNDU: `services/basis_arbitrage_strategy.py::_open_leg`
    LONG (spot) bacağı için leverage'ı HİÇ zorlamıyor —
    `services/decision_recorder.py:217`'deki `self._symbol_leverage(...)`
    genel/sembol-bazlı kaldıraç ayarını kullanıyor, yöne (spot vs perp)
    bakmıyor. Yani "LONG spot" diye adlandırılan bacak GERÇEKTE kaldıraçlı
    açılıyor ve likide olabiliyor — cash-and-carry arbitrajın temel
    varsayımı ("spot bacak likidasyon riski taşımaz") ihlal ediliyor. Bir
    bacak erken likide olunca diğeri "piyasa-nötr" değil çıplak yönlü risk
    taşımaya başlıyor — modülün kendi docstring'inin önlemeye çalıştığı
    TAM O senaryo, likidasyon yoluyla gerçekleşiyor.

    **Düzeltme:** `contracts/contexts/decision.py::Decision.leverage_
    override` yeni alanı eklendi — set edilmişse decision_recorder
    sembol/piramit/güvenlik-tavanı hesaplarının hiçbirini uygulamadan
    doğrudan kullanıyor. `_open_leg` artık LONG (spot) bacağı açarken
    leverage_override=1.0 veriyor, SHORT (perp) bacağı etkilenmiyor.
    1 yeni regresyon testi.

    **Ek bulgu (aynı gün, ayrı bug):** `close_due_pairs()` çıkış fiyatını
    SADECE Binance SPOT klines'tan deniyordu — strateji sembolleri
    futures evreninden seçildiği için birçoğu (1000000MOGUSDT, PLAYUSDT,
    4USDT vb.) spot'ta hiç yok, 400 hatası sessizce yutulup pozisyon
    max_hold_hours'ı geçtikten sonra da SONSUZA DEK açık kalıyordu
    (gerçek olay: 52 çiftten 30'u 72 saati 3+ gün aşmıştı). Çıkış fiyatı
    artık giriş fiyatıyla AYNI kaynağı (futures index_price) kullanıyor
    — hem sembol kapsamı garantili hem giriş/çıkış metodolojisi tutarlı.
    Deploy sonrası doğrulandı: 30 kilitli çift gerçek P&L ile kapandı.

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

35. **[KISMEN YAPILDI — Faz 363, 2026-08-25] Kelly/kalibrasyon örneklem
    eşiğinin kademeli artırımı.** Kullanıcı sorusu ("neden 3k yapmıyoruz")
    gerçek veriyle ölçüldü: toplam 3.302 kapanmış işlem var ama kova
    yapısı (confidence-only 10 kova, rejim×confidence 46 kova, market-cap-
    tier 18 kova, domain-bazlı 56 kova) veriyi böldüğü için tek bir büyük
    sayı TÜM mekanizmaları öldürür (ör. rejim×confidence'ta 100'de kova
    sayısı 46'dan 13'e düşüyor, kapsama %96→%74). `_MIN_BUCKET_SAMPLES`/
    `_DOMAIN_MIN_BUCKET_SAMPLES` (kelly_sizing.py + confidence_
    calibration.py, 4 sabit) 20'den **50**'ye çıkarıldı — gerçek ölçümle
    her kova tipinde kapsama %85.8-%99.9 arasında kaldı, güvenli. Kullanıcı
    kararı: veri arttıkça KADEMELİ olarak 100 → 150 → 200'e çıkılacak —
    her adımda AYNI ölçüm yöntemiyle (kova başına kapsama %) gerçek
    veriyle tekrar doğrulanmalı, körü körüne büyütülmeyecek. `weight_
    optimizer.py::MIN_SAMPLES_FOR_PROPOSAL=10`'a KASITLI dokunulmadı —
    kullanıcının kendi ayrımı: piyasa yönü/ajan ağırlıkları TAZE veriye
    (kısa pencere) duyarlı kalmalı, sadece boyutlandırma/kalibrasyon gibi
    istatistiksel-güvenilirlik gerektiren mekanizmalar büyük örneklem
    ister. 6 test (sabit `range(20)` senaryoları) 50'ye göre güncellendi.

36. **[ÇÖZÜLDÜ — Faz 363, 2026-08-25] Kelly/kalibrasyon eğrileri pump_
    fade_v1/basis_arb_v1'i izole etmiyordu.** Backlog #18 ("seçicilik
    eksik") incelenirken bulundu: bu iki mekanik strateji (AI konseyinden
    TAMAMEN izole, confidence alanını hiç doldurmuyor) round(confidence,1)
    =0.0 kovasına yığılıyordu — canlıda 199 kayıttan 197'si bunlara aitti,
    o kovanın -$236.937 zararının -$236.830'u (%99.9) pump_fade_v1
    kaynaklıydı. `kelly_sizing.py` (2 fonksiyon) + `confidence_
    calibration.py` (2 fonksiyon, biri DecisionFusion'ın EV hesabında
    GERÇEKTEN kullanılan eğri) SQL sorgularına izolasyon filtresi eklendi
    — `analytics/failure_classifier.py`/`analytics/scientific_self_
    correction.py`'nin ZATEN uyguladığı AYNI desen. Etki ölçüldü: pump_
    fade/basis_arb hariç tutulunca AI konseyinin confidence-bazlı toplam
    net PNL görüntüsü -$189.723'ten **+$47.214**'e döndü — sistem
    aslında göründüğünden daha karlı, önceki kirli görüntü yanıltıcıydı.
    4 yeni regresyon testi.

    **Backlog #18 — confidence=0.5 kovası derinlemesine incelendi, KAPATILDI
    (2026-08-26):** yapısal bir Kelly/kalibrasyon sorunu DEĞİLMİŞ. Kovanın
    zararı (-$35.467) neredeyse tamamı TEK bir alt-gruba ait: LONG+15m
    (-$37.236, diğer TÜM yön/zaman-dilimi kombinasyonları nötr/pozitif).
    O grup içinde de neredeyse tamamı TEK bir güne (23 Ağustos açılışlı,
    -$31.792) ait. O günün zararının kaynağı manual_full DEĞİL (o +$36.831
    katkı sağlıyor) — gerçek kaynak stop_loss+breakeven_stop (103 kayıt,
    -$68.623). 23 Ağustos, piramitleme rejim-kapısı düzeltmesinden (Faz
    361, "kötü fiyattan piramitleme sadece bullish_low'da izinli",
    2026-08-24 18:33'te canlıya alındı) ÖNCEKİ bir tarih — yani bu, ZATEN
    BİLİNEN ve DÜZELTİLMİŞ piramitleme sorununun geçmiş veride kalan izi.
    Ek bir müdahale (yeni gate, eşik değişikliği) GEREKMİYOR — zaman
    ilerledikçe/yeni veri biriktikçe kova kendiliğinden düzelecek.

37. **[ÇÖZÜLDÜ — Faz 363, 2026-08-26] KRİTİK: regime_reversal_guardian'ın
    streak hesabı liquidation'ı saymıyordu.** Kullanıcı bulgusu ("AI'nin
    LONG tahmini %70'ten %23'e düştü, açık pozisyonların %99'u zararda,
    geçişi iyi yönetemedi") araştırılırken bulundu. Gerçek durum: 244 açık
    pozisyon -$272.775 unrealized zarardaydı, guardian'ın streak'i sadece
    6/10 gösteriyordu (tetiklenmemiş) ama GERÇEK ardışık kayıp (liquidation
    dahil) 20'ydi — `analytics/regime_reversal.py::consecutive_stop_streak()`
    SADECE exit_reason=='stop_loss'ı sayıyordu, bir 'liquidation' streak'i
    kırıp ondan ÖNCEKİ ardışık stop_loss'ları bile saymadan durduruyordu.
    Düzeltildi: artık `analytics/failure_classifier.py::LOSS_EXIT_REASONS`
    (stop_loss/breakeven_stop/liquidation/reduced_loss_stop) ile tutarlı.
    Deploy sonrası HEMEN tetiklendi (streak=20, 1 kârdaki pozisyon
    defansif kapatıldı). 4 yeni regresyon testi.

    **Ek bulgu, backtest ile test edildi (2026-08-26): "açık pozisyonların
    toplam unrealized zararına bakan ikinci bir tetikleyici" eklemek
    KANITLANMADI.** Guardian'ın streak≥10 tetiklendiği anlarda açık olan
    pozisyonların NİHAİ sonucu (win_rate %72.5, ort. mae_pct -1.594%)
    genel LONG ortalamasından (win_rate %71.8, mae_pct -1.848%) KÖTÜ
    değil — geçmişte streak yüksekken açık kalan pozisyonlar genelde
    toparlanmış. Erken zorla kapatma karlılığı artıracağına dair kanıt
    yok, tam tersi toparlanma potansiyelini feda edebilir. Kullanıcı
    kararı: şimdilik EKLENMEYECEK, "bekleyip görelim." (Kısıt: backtest
    sadece geçmişte KAPANMIŞ pozisyonlara dayanıyor, survivorship riski var.)

38. **[ÇÖZÜLDÜ — Faz 363, 2026-08-26] "manual_full" etiketi yanıltıcıydı —
    sistemin otomatik kararlarını kullanıcı eylemiyle karıştırıyordu.**
    Kullanıcı bulgusu: "manuel kapanan pozisyon sayısı 700 küsür ama uzun
    zamandır manuel kapatmıyoruz, en son 300 küsürdü." Gerçek sayı 1505
    çıktı. Kök neden: `services/position_closer.py::close_partial()`
    exit_reason'ı HARDCODED "manual_full" idi — bu fonksiyon Faz 268'de
    SADECE gerçek kullanıcı eylemi için tasarlanmıştı ama SONRADAN (Faz
    352/362-devam) regime_reversal_guardian VE belief_reversal_exit
    (ikisi de TAMAMEN otomatik, celery görevi) tarafından da "zaten
    üretimde kanıtlanmış primitif" gerekçesiyle yeniden kullanılmaya
    başlanmıştı, hepsi AYNI etiketi üretiyordu. Düzeltildi: exit_reason
    artık çağırana özel parametre — guardian "regime_reversal_guardian",
    belief_reversal_exit "belief_reversal_exit" kullanıyor, gerçek
    kullanıcı endpoint'leri (api/rest/positions.py) hiç değişmedi. NOT:
    bu GEÇMİŞE dönük veriyi düzeltmiyor, sadece ileriye dönük kayıtları.

39. **[ÇÖZÜLDÜ — Faz 363, 2026-08-26] Meta-Learning Effectiveness paneli
    hep boş görünüyordu, kullanıcı nedenini bilmiyordu.** Fail-closed
    tasarım gereği (walk-forward Sharpe iyileşmesi eşiği +0.4, gerçek son
    ölçüm +0.002) hiç onaylı tur yoktu ama panel neden boş olduğunu hiç
    söylemiyordu. `services/meta_learning_scheduler.py` artık HER
    denemenin (başarılı/yetersiz veri/walk-forward geçemedi) son
    sonucunu `app_settings`'e yazıyor, panel boş durumda nedenini
    (son deneme tarihi, ulaşılan/gereken Sharpe iyileşmesi) gösteriyor.

40. **[ÇÖZÜLDÜ — Faz 363, 2026-08-26] "TP+SL+Manuel toplamı toplam
    işlem sayısından fazla, imkansız" — veri bozuk değil, çift sayım.**
    Kullanıcı bulgusu doğrulandı: `manual_full_count`(783) zaten
    `tp_count`/`sl_count` içine gömülü (sonucuna göre TP ya da SL
    sayılıyor), üstüne toplanırsa (2367+782+783=3932) gerçek toplamı
    (3452) aşıyor. Dashboard'daki "Manuel kapanan" kartına açıklayıcı
    alt metin eklendi ("TP/SL'ye zaten dahil.").

41. **[ÇÖZÜLDÜ — Faz 363, 2026-08-26] Opportunity Quality "high" (yüksek
    anlaşma) kovası sürekli boş.** Kısmi kök neden: `gather_opportunity_
    quality` sabit `limit=2000` kullanıyordu, `ORDER BY closed_at DESC`
    yüzünden en eski 1264 işlem (toplam 3264'ün %39'u) hiç görülmüyordu.
    `list_closed_trades` artık `list_open_positions` ile AYNI `limit=
    None` desenini destekliyor. Ölçülen etki: high kovası 8'den 15'e
    çıktı ama MIN_GROUP_SIZE=20'nin hâlâ altında — kalan boşluk yapısal
    (~9 ajanlı konseyde bu seviyeye ulaşmak neredeyse oybirliği
    gerektiriyor), veri arttıkça kendiliğinden dolacak.

42. **[ÖLÇÜLDÜ — Faz 363, 2026-08-26] Karşı-Olgusal Ajan-Etki Ölçümü —
    onchain_agent GERÇEKTEN yardımcı oluyor.** Kullanıcı sorusu:
    onchain_agent 1427 oy vermiş, 145 kez son kararı çevirmiş ama
    "caused_trade" hep 0 (~9 ajanlı konseyde tek ajanın kaldırılmasıyla
    inancın SIFIRA düşmesi yapısal olarak nadir). `analytics/
    counterfactual_trade_replay.py` + `services/counterfactual_agent_
    impact_gatherer.py` — flip vakalarını risk kapılarından
    (RiskEngine+RiskGateStage+DecisionFusion EV kapısı) geçirip
    onaylananları GERÇEK tarihsel Binance verisiyle bar-bar simüle
    ediyor (breakeven/trailing dahil). Kasıtlı basitleştirmeler
    (kullanıcı onayıyla): pozisyon büyüklüğü Kelly/CPPI/drawdown yerine
    gerçekleşen işlemin GERÇEK boyutu; risk-kapısı girdileri/kalibrasyon
    o tarihsel an yerine ŞU ANKİ canlı durum (data_leakage_caveat ile
    işaretli). Hiçbir celery task'ına bağlı değil, talep üzerine çalışır
    (Faz 284'te kaldırılan sürekli-çalışan backtest sisteminden KASITLI
    farklı). 15 yeni test.

    **Gerçek sonuç (185 flip vakası, tam tarama, 168sn):** sadece 21'i
    (%11.4) risk/EV kapılarını geçip gerçek bir işleme dönüşürdü — ham
    "145 flip" istatistiği onchain'in pratikte ne sıklıkla belirleyici
    olduğunu ciddi abartıyor. O 21 vakada: onchain OLMASAYDI win_rate
    %52.4, toplam PNL +$0.62 (neredeyse sıfır). GERÇEKTE (onchain dahil)
    aynı 21 kararın gerçek toplam PNL'i +$70.19. **Verdict: agent_helped**
    — onchain_agent kaldırılsaydı sistem ölçülebilir şekilde daha kötü
    olurdu. Örneklem küçük (n=21), veri sızıntısı çekincesi (yukarı bkz.)
    ile birlikte yorumlanmalı ama yön net.

43. **Bugünkü sabah incelemesinden kalan 3 açık madde (2026-08-26) —
    ÜÇÜ DE ÇÖZÜLDÜ (Faz 364-devam).**
    - **[ÇÖZÜLDÜ] SHORT scalp (%76.2, n=42) vs SHORT swing (%9.0, n=465)
      rejim bazlı kırılım.** `strategy_regime_compatibility_gatherer`
      zaten aynı veriyi üretiyordu, sadece rejime kırılmamıştı.
      `ai_council_SHORT_swing`'in 465 örnekleminin 409'u (%88) `bearish_
      low` rejiminde — win_rate %5.4, tam Faz 342'nin zaten bulup
      gate'lediği "SHORT+bearish+low volatility" havuzu (n=424, %8.3),
      YENİ bir sorun değil. Kalan `bearish_normal` (n=35) %34.3 — daha
      iyi ama hâlâ zayıf, küçük örneklem (CI %20.8-%50.9), izlemede kalsın.
    - **[ÇÖZÜLDÜ] Onchain/credit/volatility/relative_strength "mimari
      bağlantı" kaygısı — gerçek bir sorun değildi.** `explain_position`
      domain-agnostic, gerçek kararlarda tüm domain'ler mevcut, frontend
      hardcoded filtre yok. İlk kontrolümdeki "hiç yok" görüntüsü kendi
      ORDER BY'sız/LIMIT'li sorgumun örneklem hatasıydı.
    - **[ÇÖZÜLDÜ — GERÇEK KÖK NEDEN BULUNDU] Technical dışındaki domain'lerin
      kalibrasyon modeli eksikliği.** Aslında macro/onchain/order_flow/
      pattern/quant/relative_strength/sentiment'ın HEPSİNDE artık gerçek
      eğrisi var (veri o zamandan beri büyüdü) — sadece **credit** ve
      **volatility** hâlâ yok. Gerçek kök neden: bu iki ajan, canlıya
      alındıklarından (21 Ağustos) bugüne kadar ~38.000 kararın TAMAMINDA
      WAIT oyu vermiş — TEK BİR KEZ bile LONG/SHORT dememişler (SQL ile
      doğrulandı). Sebep: `volatility_agent.py`'nin DVOL eşiği (24 saatte
      >%15 hareket) ve `credit_agent.py`'nin yield-curve-inversion/spread
      eşiği kasıtlı olarak SADECE aşırı/nadir rejim değişimlerini
      puanlıyor (onchain'in MVRV/NUPL/SOPR'daki AYNI "sadece aşırılık"
      disiplini) — 5-6 günlük kısa canlı geçmişte bu eşikler hiç
      aşılmamış. Madde 44'teki kullanıcı hipotezini doğruluyor: credit/
      volatility'nin "sessizliği" ile kalibrasyon eksikliği AYNI kök
      nedene bağlı. **Karar kullanıcıya bırakıldı** — eşikleri gevşetmek
      (daha sık ama daha zayıf sinyal) mi, yoksa gerçek bir rejim
      değişimi olana kadar beklemek mi (mevcut tasarım) tercih edilir,
      henüz uygulanmadı.

44. **Karşı-Olgusal Ajan-Etki Ölçümü — credit/volatility/relative_strength
    turu (2026-08-26), henüz araştırılmadı.** Madde 42'nin AYNI aracıyla
    (`analytics/counterfactual_trade_replay.py`) kullanıcı 3 ajanı daha
    taradı, üçü de birbirinden çok farklı bir tablo çizdi:
    - **credit ve volatility**: tüm geçmişte SADECE 1 kez (her biri)
      council'in son yönünü çevirmiş, o tek vaka da risk kapılarını
      geçmemiş — gerçek işleme hiç dönüşmemiş. Örneklem o kadar küçük ki
      "inconclusive" (agent_helped/agent_hurt ölçülemez).
    - **relative_strength**: 154 flip, 12'si gerçek işleme dönüşmüş.
      Ajan OLMASAYDI o 12 kararın toplam PNL'i +$0.61 (sıfıra yakın),
      GERÇEKTE (dahil) +$879.85 — madde 42'deki onchain bulgusundan
      (+$0.62 → +$70.19) bile çok daha çarpıcı bir fark. **agent_helped**,
      güçlü sinyal.
    - Kullanıcının hipotezi: credit/volatility'nin bu kadar "sessiz"
      kalması, madde 43'ün son alt maddesiyle (technical dışındaki 5
      domain'in hiç kalibrasyon modeli olmaması) aynı kök nedene işaret
      ediyor olabilir — bu iki ajan için kalibrasyon modeli eğitecek
      anlamlı/yeterli sinyal baştan hiç oluşmuyor olabilir. Kullanıcı
      kararı: şimdi değil, "bir ara" bakılacak.

45. **[ÇÖZÜLDÜ — Faz 364, 2026-08-26] KRİTİK: pump_fade_enabled=true
    ayarına rağmen sistem hiç pozisyon açmıyordu.** Kök neden: circuit
    breaker (`pump_fade_max_loss_circuit_breaker_usd`, eşik $10K) her
    `run_cycle()`'da kümülatif TÜM ZAMANLARIN gerçekleşmiş zararına
    ($269K+) bakıyordu — bu zararın tamamı 20 Ağustos'ta (Faz 332
    düzeltmesinden ÖNCE, o zamanki tavansız formülle) açılmış ~82 legacy
    pozisyondan, 21 Ağustos'tan beri TEK bir yeni pozisyon yokken. Ayarı
    `true` yapmak işe yaramıyordu çünkü her cycle kendini yeniden
    `false`'a çekiyordu. Çözüm: `kill_switch_legacy_cutoff_at` ile AYNI
    desen — yeni `pump_fade_circuit_breaker_legacy_cutoff_at` ayarı
    (21 Ağustos'a set edildi), bu tarihten önceki pozisyonlar devre
    kesici toplamına hiç girmiyor (dashboard/istatistikler etkilenmedi).
    Canlıda doğrulandı: artık `candidates_found` ile gerçek tarama
    yapıyor.
46. **[YAPILDI — Faz 364, 2026-08-26] Basis Arbitrage stratejisi
    tamamen kaldırıldı.** Kullanıcı bulgusu: 90 kapanmış işlem, toplam
    gerçekleşmiş P&L -$196.52 (net zarar) — $100/bacak boyutunda
    komisyonlar funding+basis kâr payını aşıyordu. AI konseyinden
    tamamen izole mekanik bir strateji olduğu için (hiçbir kalibrasyon/
    öğrenme döngüsüne veri beslemiyordu) "veri toplama" gerekçesi de
    yoktu. Önce tüm açık pozisyonlar kapatıldı (23 eşleşmiş çift +
    4 yetim bacak, gerçek güncel fiyattan), sonra kod tabanının her
    yerinden silindi: `services/basis_arbitrage_strategy.py`,
    `market_data/basis/`, `tests/test_basis_arbitrage_strategy.py`
    kaldırıldı; celery task/beat girişleri, Settings ayarları+UI kartı,
    API validasyonu kaldırıldı; `confidence_calibration.py`/
    `kelly_sizing.py`/`strategy_regime_compatibility_gatherer.py`'deki
    (artık silinmiş modülden) import'lar sabit string'e çevrildi (geçmiş
    kapanmış basis_arb_v1 kararları hâlâ DB'de, izolasyon/etiketleme
    hâlâ doğru çalışıyor). 1812 test hatasız collect ediliyor, tsc temiz.
47. **[YAPILDI — Faz 364, 2026-08-26] pump_fade Kademeli Giriş (Staged
    Entry).** Kullanıcı fikri, gerçek Binance verisiyle kalibre edildi
    (43 sembol, 250 gün, 15 bağımsız +%50 pump olayı): entry'den sonra
    fiyat medyan +%36, p90 +%82 DAHA yükseliyor, ama +%90'a örneklemde
    HİÇ ulaşılmıyor (0/11). Dip-bazlı %50'de hedefin %25'i açılır (stop'a
    mesafe uzak, güvenli kaldıraç ~2.5x); dip-bazlı %80'e ulaşırsa 3 katı
    büyüyüp %100'e tamamlanır (bu ikinci bacak, ortak stop'a mesafesi çok
    yakın olduğu için ~11x kaldıraç kaldırabilir — kullanıcının orijinal
    "yüksek kaldıraç" fikri, doğru mesafeyle, tutarlı çıktı); ortak stop
    dip-bazlı %90'da. Risk bütçesi (`max_loss_per_trade_usd`) iki bacak
    arasında `first_leg_pct`'e göre bölünür, toplamda normal (kademesiz)
    bir işlemle AYNI $ tavanı. Migration (2 yeni nullable kolon), yeni
    Celery görevi (add-tetiği taraması, 60sn), Settings kartı. Kullanıcı
    onayıyla canlıya alındı (`pump_fade_staged_entry_enabled=true`,
    `pump_fade_enabled=true`). 7 test.

    **Yan bulgu (canlı restart sırasında):** celery worker'lar 17:02'de
    (nedeni belirsiz) yeniden başlamıştı ama celery beat Pazartesi'den
    beri hiç başlamamıştı — beat hâlâ silinmiş `run_basis_arbitrage_
    cycle_task`'ı kuyruğa koymaya devam ediyordu, eski worker'lar (17:02
    öncesi) bunu son kez çalıştırıp 11 gerçek basis-arb çifti açtı
    (ve `max_hold_hours=0` kalıntı ayarım yüzünden saniyeler içinde
    kendilerini kapattı). Ayrıca AYNI eski worker, circuit breaker
    düzeltmesi (madde 45) yüklenmeden ÖNCE bir kez daha tetiklenip
    `pump_fade_enabled`'ı false'a çekmişti. Kullanıcı onayıyla celery
    worker+beat TAMAMEN yeniden başlatıldı (iki kez — #13/#14 kodu da
    dahil olsun diye) — artık hem basis-arb hem eski circuit breaker
    sorunu kalıcı olarak temiz. **Ders:** kod değişikliği sonrası SADECE
    worker değil, celery BEAT de yeniden başlatılmalı — schedule dict'i
    sadece beat'in kendi başlangıcında yükleniyor, worker restart'ı
    yetmiyor.

48. **[YAPILDI — Faz 364, 2026-08-26] Ajan Güvenilirliği × Rejim ölçümü.**
    Kullanıcı sorusu: "hangi ajan hangi rejimde isabetli, ölçmezsek şu an
    zayıf görünen bir ajanı boşuna silebiliriz." Gerçek bir boşluktu —
    `strategy_regime_compatibility` (strateji×rejim) ve `agent_combination_
    reliability` (ajan-ikilisi×genel) vardı ama ajan-domain×rejim yoktu.
    `services/agent_domain_regime_reliability_gatherer.py`, YENİ saf
    fonksiyon YAZMADAN `compute_strategy_regime_compatibility`'yi "strategy"
    etiketi yerine ajan domain'i ile besleyerek çözdü. Genel Özet'e 18.
    modül olarak eklendi. Gerçek örnek: `relative_strength` genelde %52.7
    (vasat) ama `bullish_low`'da %68.5, `bullish_high`'ta %39.5 — genel
    ortalama rejim-özel değeri gizliyor.
    **Doğal sonraki adım (henüz YAPILMADI, ayrı karar gerektirir):**
    kullanıcının önerdiği gibi ajan ağırlıklarını rejime göre otomatik
    ayarlayan bir mekanizma (`moe_regime_router.py`'nin hurst-bazlı tilt
    deseniyle benzer ama bu ÖLÇÜLMÜŞ veriye dayanır) — "yeni karmaşıklık
    kendi edge'ini kanıtlamalı" ilkesi gereği önce daha büyük örneklemle
    (şu an bazı domain×rejim hücreleri 15-20 işlem civarında, ince) ve
    gerçek OOS doğrulamayla desteklenmeli, hemen wire edilmedi.

49. **[VERİ TOPLAMA KISMI YAPILDI — Faz 365, 2026-08-26] Liquidation
    Agent (eski adı "MempoolAgent" — kullanıcı onayıyla değiştirildi,
    gerçek veri kaynağı mempool değil).** Ham Ethereum gas verisi
    (`fetch_eth_gas_price_gwei`) zayıf proxy'ydi. Kullanıcı kararı:
    "veri toplayıp ölçebiliyorsak iyi, en önemli kısım orası — wire
    etmesi kolay." Kurulan: `liquidation_events` tablosu (migration
    faz365, TimescaleDB hypertable, hem quantdb hem quantdb_test'e
    uygulandı) + `services/binance_liquidation_listener.py` (Binance'in
    ücretsiz `!forceOrder@arr` akışı, `realtime_position_monitor.py`
    ile AYNI kalıcı-süreç deseni, `service_watchdog.sh`'a eklendi) +
    `market_data/liquidations/liquidation_provider.py` (okuma/toplama
    katmanı, `fetch_liquidation_pressure(symbol, window_minutes)`).
    9 test. Canlıda doğrulandı: watchdog yeniden başlatıldı, dinleyici
    bağlandı, elle test satırıyla INSERT yolu doğrulandı (gerçek akışta
    ilk ~50sn'de olay gelmedi — piyasa şu an sakin, credit/volatility
    ajanlarının aynı dönemdeki sessizliğiyle tutarlı, alarm değil).
    **Henüz YAPILMAYAN**: `LiquidationAgent` (oy veren ajan sınıfı) +
    `AgentDomain` üyesi + council'e wire etme — kullanıcı isteğiyle ayrı
    bir tur, önce veri birikmesi bekleniyor.

50. **[AÇIK] "bearish_low" rejiminde LONG/SHORT arasında çarpıcı ters
    ilişki — muhtemelen EMA20/50 lag artefaktı, kök neden HENÜZ
    doğrulanmadı.** Kullanıcı hipotezi (2026-08-26): SHORT swing'in
    çöküşü (madde 28/43) belki AYNI rejimde başarılı olan bir zıt-yön
    ile bağlantılı. Gerçek veriyle doğrulandı — AYNI `bearish_low`
    etiketinde: SHORT swing win_rate %5.4 (n=409) ama LONG swing %85.9
    (n=142) VE LONG scalp %96.5 (n=342). Kod incelemesi (`market_data/
    features/signal_engine.py:83`): trend etiketi `ema20 > ema50 ->
    bullish, < -> bearish` klasik bir GECİKMELİ (lagging) crossover —
    "bearish" tetiklendiğinde fiyat genelde zaten en sert düşüşünü
    yapmış, dip'e yakın/geçmiş oluyor olabilir (LONG'un neden bu
    etikette bu kadar iyi olduğunu, SHORT'un neden kötü olduğunu
    mekanik olarak açıklayabilir). **Henüz doğrulanmadı** — gerçek
    kontrol: `bearish_low` etiketlenen kararların EMA20/50 crossover'a
    göre kaç bar/saat önce gerçekleştiğini gerçek fiyat verisiyle
    ölçmek gerekiyor. Doğrulanırsa bu "yeni bir alpha" değil, mevcut
    SHORT-blokaj kapısının (madde 23, Faz 361) NEDEN doğru olduğunun
    mekanik açıklaması olur — kullanıcının "geniş bir rejim-korelasyon
    modülü" fikri yerine, ÖNCE bu tek hipotez ucuz bir sorguyla test
    edilmeli (yeni bir genel-amaçlı modül inşa etmeden önce).

    **[ÇÖZÜLDÜ — ölçüm tarafı, Faz 364-devam] `direction_regime_asymmetry`
    modülü kuruldu.** Dar EMA-lag hipotezi TEST EDİLDİ ve DOĞRULANMADI —
    bearish_low'daki SHORT kararlarının 20-bar fiyat aralığındaki
    konumuna bakıldı (dip'e yakınken daha kötü olması beklenirdi),
    gerçek sonuç TERSİ çıktı (dip'e yakın %9 win, üst kısımlarda %0 win)
    — SHORT bu rejimde aralığın HER YERİNDE çöküyor, salt gecikme
    açıklamıyor. Bunun yerine kullanıcının "geniş korelasyon modülü"
    fikri kuruldu: `analytics/direction_regime_asymmetry.py` (yeni DB
    sorgusu YOK, `strategy_regime_compatibility`'nin çıktısını LONG/
    SHORT çiftleri halinde eşleştiriyor) + Genel Özet'e 19. panel. Gerçek
    sonuç: swing/bearish_low LONG %85.9 vs SHORT %5.4 (80 puan fark),
    swing/bearish_normal 57 puan, scalp/bearish_low 22 puan. 8 test.
    **Aksiyon tarafı KASITLI OLARAK YAPILMADI** — kullanıcı kararı
    (2026-08-26): "örneklem büyüsün sonra karar verelim, bir ara tekrar
    bakılacak." Madde 23'teki `pyramid_regime_gate.py` deseni (en
    performanslı rejimde izin ver, dışında yasakla) burada da uygulanabilir
    ama HENÜZ uygulanmadı — sadece ölçüm canlı.

51. **[ÖLÇÜLDÜ — Faz 366-devam, 2026-08-27, ETKİ İHMAL EDİLEBİLİR
    ÇIKTI] OnChain'in BTC-özel ağ sağlığı sinyalleri (network_activity_
    trend/hash_rate_trend) diğer sembollerde de puana katılsaydı?**
    Kullanıcı sorusu (2026-08-26). NOT: bu ZATEN bilinçli bir kısıtlama —
    Faz 248 bulgusu bunun tam tersini bir hata olarak bulup düzeltmişti.
    Test yöntemi: `counterfactual_trade_replay.py`'nin leave-one-out'undan
    FARKLI bir "ne olurdu" simülasyonu kuruldu —
    `analytics/onchain_extension_counterfactual.py` (saf, agents/onchain_
    agent.py'nin BİREBİR AYNI eşikleriyle onchain oyunu hipotetik olarak
    genişletiyor) + `services/onchain_extension_counterfactual_gatherer.py`
    (her BTC-dışı kararı, en yakın zamanlı GERÇEK bir BTC kararının
    saklı `feature_contributions`'ıyla besleyip `BeliefEngine().
    synthesize()` ile council'i yeniden çalıştırıyor — yeni bir
    tarihsel API çekme gerekmedi). `services/counterfactual_agent_
    impact_gatherer.py::replay_flipped_decision`'a `resynth` parametresi
    eklenerek (geriye dönük uyumlu) ~150 satırlık bar-bar risk/execution
    replay TEKRARLANMADI.

    **Gerçek sonuç: etki neredeyse yok.** 3140 BTC-dışı kararın SADECE
    32'si (%1.0) yön değiştirirdi, o 32'nin de sadece 5'i risk/EV
    kapılarından geçip gerçek bir işleme dönüşürdü (27'si reddedildi/
    veri yetersiz) — n=5, anlamlı bir istatistik için gerekli eşiğin
    (10) çok altında, **verdict=inconclusive** (fail-closed, zorla bir
    sonuç üretilmedi). Pratik sonuç: kısıtı açmanın getirisi o kadar
    nadir ki (ayda ~1 kararda 1) zahmete değmez — Faz 248'in kararı
    doğru, yeniden açılmasına gerek yok. 4 test.

52. **[AÇIK, ÇOĞU HENÜZ DOĞRULANMADI] Harici GPT incelemesi — "Research
    Control Plane" raporu (2026-08-26).** Genel Özet panellerinin
    canlı çıktısına bakarak yazılmış 20 maddelik bir rapor + öncelik
    sırası. Rapor kendi önerdiği sırayla:

    **P0 (önce):**
    - **[DOĞRULANDI, GERÇEK BUG] Risk Simülatörü (`market_world_model`)
      -1748% gibi imkansız görünen değerler üretiyor.** Kök neden
      bulundu: `analytics/market_world_model.py` doğru compounding
      yapıyor (toplama değil), AMA `services/market_world_model_
      gatherer.py:39`'un beslediği `returns` ham VARLIK fiyat getirisi
      (`sign * (exit-entry)/entry`) — leverage/margin'e göre ayarlanmış
      gerçek pozisyon PnL%'i DEĞİL. Varlık %100'den fazla hareket eden
      bir SHORT'ta bu -1.0'dan daha negatif bir "getiri" üretiyor,
      compounding formülü `(1+r)>0` varsayımını kırıp işaret değiştiren
      anlamsız kümülatif değerler veriyor.
      **[DÜZELTİLDİ — Faz 366-devam, 2026-08-27]** Kullanıcı kararı:
      taban/cap yerine gerçek margin-bazlı PnL%. İlk deneme (`pnl/margin`)
      TEK BAŞINA yetersiz çıktı, iki AYRI ek sorun ortaya çıkardı: (1) bu
      fonksiyon `pump_fade_v1`'i hariç tutuyordu ama `basis_arb_v1`'i HİÇ
      tutmuyordu — basis_arb_v1 (Faz 364'te kaldırıldı, backlog #30'da
      bilinen likidasyon-gecikmesi hataları var, gerçek örnek: BTRUSDT
      SHORT margin=$100 ama pnl=-$1864, 18.6x) `confidence_calibration.py`/
      `kelly_sizing.py`'nin (Faz 363, #36) zaten uyguladığı izolasyonu
      kaçırmıştı, eklendi. (2) `pnl/margin` ile bile 50 işlemi ardışık
      compound etmek anlamsız kaldı (ortalama %744 trilyon!) — her
      seferinde TÜM bakiyenin yeniden 5-10x kaldıraçla yatırıldığını
      varsayıyordu, sistemin gerçek boyutlandırmasıyla (capital_per_trade,
      sermayenin küçük bir dilimi) uyuşmuyordu. Gerçek düzeltme: payda
      `starting_capital` (`backtest/red_team.py`'nin AYNI "sabit taban
      sermaye" ilkesi) — gerçek veriyle doğrulandı, artık ortalama
      %0.0012, en kötü -%0.6 (önceden trilyonlarca/imkansız). 2 yeni
      test (paylaşılan quantdb_test'in bilinen kirliliğinden izole,
      monkeypatch'li). uvicorn+celery worker+beat yeniden başlatıldı.
    - Stop execution audit — "810 stop-kapanışının %27'si (216) gerçek
      stop seviyesini aşarak kapanmış, en kötü %12" iddiası — bu
      oturumda DOĞRULANMADI (rapor bir dokümandan aldığını söylüyor,
      koda bakılmadı). Gerçekse ciddi — her stop için intended_stop/
      trigger/fill/slippage ayrıştırılmalı.
    - Decision Transformation Ledger — her kararın raw→calibrated→
      regime→Kelly→ENB→correlation→meta-label→final boyutlandırma
      zincirini DB'ye kaydetmek. Fikir sağlam, henüz yok.
    - Self-Model → risk governor (boyut çarpanı) — ÖNCE reliable/
      degraded/unreliable gruplarının OOS PnL farkı ölçülmeli, kafadan
      katsayı YASAK. `[[project_closed_loop_self_optimization_vision]]`
      hafıza notuyla aynı vizyon.

    **P1:** Quant Agent Ablation 2.0 (ON/OFF/ONLY + ΔPnL/ΔSharpe/Δdrawdown,
    sadece accuracy değil), **Opportunity Quality edge decay testi**
    (eskiden medium≫low idi, hâlâ öyle mi? — ucuz, Scientific Self-
    Correction'a çok uygun, öncelikli), MAE/MFE `insufficient_data`
    kök neden izi, TP/SL Confluence %0 uçtan uca 5 gerçek trade ile
    elle izleme (geçmişte stop_loss_price distance/absolute karışıklığı
    GERÇEKTEN yaşanmıştı — GPT bunu doğru hatırlıyor).

    **P2:** Meta-learning objective'i Sharpe yerine robust_score (OOS
    Sharpe - λ·drawdown - λ·tail_loss - λ·turnover) yapmak + "peak değil
    plateau" stabilite testi, signal persistence N eşiği için de AYNI
    plateau mantığı (N=6 tek nokta değil, 5-8 aralığı), conditional
    edge map (`agent_domain_regime_reliability`/`direction_regime_
    asymmetry` ZATEN bu yönde, rapor bunlardan habersiz paralel
    düşünmüş), Direction Prediction V2 için kalibrasyon eğrisi (sadece
    Brier değil).

    **Rapor kendi kararıyla ERTELEDİĞİ şeyler** (kullanıcının `[[feedback_
    no_new_agents_focus_on_hardening]]` prensibiyle bağımsız olarak
    örtüşüyor — dikkat çekici): yeni ajan, yeni LLM/embedding, Quantum/
    Adversarial ajan, otomatik CMA-ES onayı, Self-Model'in doğrudan yön
    değiştirmesi.

    **Genel değerlendirme:** raporun "gate interaction" endişesi (#13 —
    çok fazla çarpımsal shrinkage bir trade'i fark edilmeden öldürüyor
    olabilir) ilginç ama henüz ölçülmedi. "Research Control Plane"
    mimari önerisi (#20) kavramsal olarak makul ama var olan modüllerin
    çoğu ZATEN o diyagramın parçaları — yeniden mimarilemek yerine önce
    modüller-arası etkileşimi ölçmek daha ucuz bir ilk adım olabilir.

53. **[AÇIK, sonra bakılacak] İki paralel rejim taksonomisi.** Kodda
    GERÇEKTEN iki ayrı rejim sınıflandırması var: `market_regime` (DB
    sütunu, `signal_engine.py`'nin EMA20/50-benzeri hızlı `trend` +
    `volatility_regime`'inden — bugün kurulan tüm yeni paneller
    (`agent_domain_regime_reliability`, `direction_regime_asymmetry`,
    `feature_ic_by_regime`) bunu kullanıyor) VE `long_term_trend_regime`
    (200-EMA tabanlı, yavaş — `barrier_table_builder.py`/MAE-MFE
    Confidence paneli, `meta_label_model.py`, `quant_agent.py` bunu
    kullanıyor). GPT raporunun #7'deki "mimari smell" sezgisini kısmen
    doğruluyor ama kök neden bir bug değil — bilinçli olarak iki farklı
    zaman ölçeğinde iki ayrı sinyal. Yine de kafa karıştırıcı, aynı
    kelime ("rejim") iki farklı şey ifade ediyor. Kullanıcı kararı:
    "todoya not alalım sonra bakarız" — henüz araştırılmadı/birleştirilmedi.

54. **[YAPILDI — Faz 366, 2026-08-26] Strategy Gate Approval — insan
    onaylı strateji×rejim engelleme mekanizması.** Kullanıcı: "ürettiği
    strateji insan onayına sunulur böyle bir yapı ayarlamıştık... veri
    toplamanın mantığı yok kullanmıyorsak." Kontrol edildi: böyle bir
    yapı YOKTU — `WeightApproval`/`PendingApprovals.tsx` SADECE ajan
    ağırlıkları içindi, `strategy_hypothesis_scanner.py`'nin (Faz 346)
    bulduğu adaylar için hiç onay kuyruğu yoktu. `weight_approvals` ile
    AYNI propose→pending→approve/reject desenini kurduk:
    - `strategy_gate_approvals` tablosu (migration faz366, hem quantdb
      hem quantdb_test).
    - `services/strategy_gate_proposer.py`: `scan_for_gate_candidates` +
      `validate_candidate_out_of_sample`'ı çalıştırıp SADECE OOS'ta
      tekrarlanan (`replicated_out_of_sample=True`) adayları pending
      olarak kaydeder, dedup var (Faz 229 disiplini). Günlük Celery
      görevi (`propose_strategy_gate_candidates_task`) + `auto_reject_
      stale_strategy_gate_approvals_task` (24s).
    - `analytics/strategy_regime_gate.py::is_strategy_regime_gated()` —
      saf fonksiyon, engellenmiş (strateji, rejim) kümesinde eşleşirse
      engeller.
    - `decision_recorder.py`'ye wire edildi — `stop_loss_price`
      hesaplandıktan SONRA (trade_type ona bağlı, `pyramid_regime_
      gate`'in aksine daha geç bir noktada). Yeni ayar `strategy_gate_
      enabled` (varsayılan true).
    - `api/rest/strategy_gates.py` (pending/blocked/approve/reject) +
      `PendingApprovals.tsx`'e ikinci bölüm eklendi ("Strateji Kapı
      Adayları").
    - **[DÜZELTME, aynı gün] İsimlendirme hatası bulundu ve düzeltildi:**
      kullanıcı bulgusu — `status="approved"` yanlış okunuyordu ("onaylı
      strateji" = "kazandıran strateji" gibi algılanabiliyordu, oysa
      onaylanan şey stratejinin İYİLİĞİ değil, o rejimde ENGELLENMESİ).
      Statü değerleri `approved`→`blocked`, `rejected`→`dismissed`
      olarak değiştirildi (repository/API/testler/canlı DB satırı dahil
      TÜM katmanlarda), approve()/reject() fiil olarak kaldı ama sonuç
      durumu artık ters okunamıyor.
    - **İlk gerçek aday, bu oturumda insan kararıyla (kullanıcı, canlı
      konuşmada) engellendi ve şu an CANLI engelliyor:**
      `ai_council_LONG_swing` × `bullish_high` (win %64.6 vs geri kalan
      %90.7, p=0.0, OOS'ta tekrarlandı) — `strategy_hypothesis_scanner`
      panelinin BULDUĞU, kimsenin daha önce fark etmediği bir bulguydu.
    - 24 test (pure/repository/wiring), hepsi geçti. uvicorn+celery
      worker+beat üçü de yeniden başlatıldı, temiz.

55. **[YAPILDI — Faz 366-devam, 2026-08-27] Varlık Sınıfına Göre AI
    Başarı Oranı — Dashboard bilgilendirme kartı.** Kullanıcı isteği:
    "Bitcoin/Emtia/Hisse performansını... hangi işlem türünde AI ne
    kadar başarılı, kısaca bakış atabilirim." `services/agent_memory.py::
    asset_class_of_symbol()` (Faz 325'te market-cap kalibrasyonu için
    kurulmuştu) 3 kaba kategoriye (Kripto/Emtia/Hisse Senedi) gruplanıp
    win_rate + Wilson güven aralığı hesaplandı — yeni bir sınıflandırma
    icat edilmedi. `analytics/asset_class_performance.py` (saf) +
    `services/asset_class_performance_gatherer.py` (pump_fade_v1/
    basis_arb_v1 hariç, agent_combination_reliability ile AYNI izolasyon)
    + `GET /api/v1/dashboard/asset-class-performance` + Dashboard.tsx'e
    "AI Şu An Piyasa Yönünü Nasıl Görüyor" kartının hemen altına yeni
    kart. Gerçek veri çarpıcı: **Emtia %98.2** (n=282), **Kripto %68.5**
    (n=2848), **Hisse Senedi %53.9** (n=65, geniş GA). 6 test + uçtan
    uca gerçek HTTP isteğiyle doğrulandı, tsc temiz. Tarayıcıda görsel
    doğrulama YAPILMADI (dev server başlatılmadı).

56. **[YAPILDI — Faz 367, 2026-08-27] LLM sistemi mimariden tamamen
    kaldırıldı.** Kullanıcı: "LLM'i kaldıracağız, 5 gündür zaten
    çalışmıyor, çalışsa da işe yarar bir tavsiyede bulunduğu hiç olmadı.
    Mimariyi şişiriyor gereksiz, bizim ajanlar daha iyisini yapabilir."
    Gerçek doğrulama: `llm_audit_runs`'ta 30/30 çalıştırmada
    `proposals_created=0`, son gerçek çalıştırma TAM 5 gün önce hata ile
    durmuş (`[Errno 2] No such file or directory`), canlı test edilen
    NVIDIA API çağrısı `ReadTimeout` ile başarısız oldu. sentiment_agent
    zaten Faz 269-sonrası'nda 9 oy-veren ajan listesinden çıkarılmıştı —
    `refresh_llm_news_sentiment_task`'ın ürettiği veriyi tüketen hiçbir
    şey kalmamıştı (ölü kod).

    Silinen: `llm_reasoner.py`, `llm_tools.py`, `services/llm_system_
    audit.py`, `market_data/sentiment/llm_news_sentiment_provider.py`,
    `contracts/llm_audit_run.py`, `contracts/code_change_proposal.py`,
    `contracts/llm.py`, `database/repositories/llm_audit_run_repository.py`,
    `database/repositories/code_change_proposal_repository.py`,
    `api/rest/llm_critic.py`, `dashboard/src/views/LLMCritic.tsx`,
    `meta_optimizer/orchestrator.py`/`analyzer.py` (doğrulanmış dead
    code — hiçbir live servis import etmiyordu, sadece `contracts.llm`'e
    bağımlıydı). `llm_system_audit_task`/`refresh_llm_news_sentiment_task`
    (+ ilgili celery beat/queue routing girdileri, "slow" kuyruğu artık
    boş ama ders yorumla korundu) + `/news-sentiment` endpoint'i +
    MarketOverview.tsx'teki "Piyasa Haber Duyarlılığı" kartı + Sidebar/
    App.tsx route'u temizlendi. Migration faz367: `llm_audit_runs` +
    `code_change_proposals` tabloları drop edildi (hem quantdb hem
    quantdb_test). 7 test dosyası silindi, 2 test dosyasında ilgili
    testler çıkarıldı. 1832 test hatasız collect ediliyor, tsc temiz,
    uvicorn+celery worker+beat yeniden başlatıldı, temiz.

57. **[YAPILDI — Faz 367, 2026-08-27] Varlık Sınıfı + Rejim Aç/Kapa
    Modülleri — Dashboard kartlarına yerleştirildi.** Kullanıcı isteği:
    "Emtia, Token ve Hisse Senedi'ni aç kapa yapabileceğimiz modüller...
    Settings yerine dashboard'daki karta yerleştirelim" + "sistemin
    işlem aldığı rejimleri de aç kapa yapabilirsek süper olur." Settings
    yerleşimi YERİNE kontekstüel (bkz. proje hafızası "settings
    placement: contextual"):
    - `services/agent_memory.py::asset_class_trading_category()` — TEK
      kaynak (crypto/commodity/equity), `analytics/asset_class_
      performance.py`'nin görünen etiketiyle (Kripto/Emtia/Hisse Senedi)
      AYNI sınıflandırmayı paylaşıyor.
    - `analytics/asset_class_trading_gate.py` + `analytics/regime_
      trading_gate.py` (saf, fail-OPEN — bunlar güvenlik kapısı değil,
      kullanıcı tercihi) + `decision_recorder.py`'ye wire (asset-class
      pump_fade'i de kapsıyor, regime SADECE AI konseyi).
    - Yeni ayarlar: `asset_class_trading_enabled`, `regime_trading_
      enabled` (JSON map, `symbol_leverage` ile AYNI desen).
    - Dashboard.tsx: asset-class kartına aç/kapa düğmeleri eklendi, YENİ
      bir "Rejime Göre AI Konseyi Girişleri" kartı (6 rejim, aç/kapa).
      Mevcut `save()`/settings fetch'i yeniden kullanıldı, yeni API
      YAZILMADI (generic `/api/v1/settings/{key}` yeterliydi).
    - 21 test, tsc temiz, uçtan uca gerçek HTTP isteğiyle doğrulandı
      (bir ad-hoc doğrulama scripti yanlışlıkla üretime yazdı, hemen
      fark edilip doğru varsayılana geri alındı — bkz. proje hafızası
      "debug scripts must target test db").

## Notlar

- Kullanıcı `max_open_positions_per_symbol_direction`'a (1000) bilerek
  dokunmamamızı istedi — test modunda gereksiz kısıtlama. Madde 4 (fiyat bazlı
  kontrol) bundan AYRI, hâlâ geçerli bir istek.
- Faz 353 (`moe_regime_router`) bu turdan önce zaten wire edildi ve commit
  edildi — ayrı.
