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

## 🔴 Doğrulandı, gerçek — yüksek öncelik

3. **Confidence timeline parçalanmış (harici incelemenin #1/#2 maddesi — kodla
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
   **Önerilen yaklaşım (tartışılacak):** portföy fusion indirimini MetaStage'den
   SONRA ama act_threshold kontrolünden ÖNCE taşımak, ya da indirim sonrası
   threshold'u yeniden kontrol edip düşerse WAIT'e çevirmek.

4. **Aynı sembolde tekrar aynı yönde pozisyon açarken elindeki pozisyonun giriş
   fiyatı hiç kontrol edilmiyor (kullanıcı örneği: $5→$7→$9 LONG piramitleme).**
   Şu an `max_open_positions_per_symbol_direction` sadece SAYIYI sınırlıyor
   (ve kullanıcı isteğiyle 1000'de bırakıldı, test modunda dokunulmuyor) — fiyata
   hiç bakmıyor. Gerçek istek: aynı yönde zaten AÇIK bir pozisyon varsa ve yeni
   giriş fiyatı elindeki pozisyon(lar)ın ortalamasından/en pahalısından daha
   kötüyse (LONG'da daha yüksek, SHORT'ta daha düşük), YENİ pozisyonu reddet ya
   da en azından WAIT'e zorla. Henüz hiçbir yerde böyle bir kontrol yok — kod
   incelemesiyle doğrulandı (risk_state.py/cognitive_pipeline.py'de sadece sayı
   bazlı gate var, fiyat bazlı yok).

5. **Kâr koruma / trailing yok — 10k kârdan başa-başa kadar bekliyor.**
   Kod incelemesi teyit ediyor: `PositionCloser`/`RiskTargetStage` sadece sabit
   stop/target ve (varsa) breakeven tetikleyicisiyle çalışıyor, gerçekleşmemiş
   kârın tepe noktasından ne kadar geri çekilmeye izin verileceğine dair (trailing
   stop / kâr kilitleme) hiçbir mekanizma yok.

## 🟡 Doğrulanmadı ama muhtemelen doğru — harici incelemenin kalan maddeleri

Bunları teker teker kodla doğrulamadım (zaman/kapsam), ama #1'i doğrulayan aynı
inceleme olduğu için güvenilirlik yüksek varsayıyorum, sıradaki turlarda tek tek
gerçek kodla teyit edilecek:

6. REDUCE kararı recorder'da normal pozisyon açılışıyla aynı yolu izliyor
   (`action=="REDUCE"` kontrolü yok, sadece `final_size>0` kontrolü var) —
   "küçült" niyeti "küçük aç" davranışına dönüşüyor olabilir.
7. Agent-agreement sinyali hem DecisionFusion'da (confidence çarpanı) hem
   RiskTarget/meta-label'da (boyut çarpanı) AYRI AYRI uygulanıyor — aynı düşük-
   agreement durumu iki kez cezalandırılıyor olabilir (bug değil ama üst üste
   binme riski).
8. Episodic memory / `_persist_and_learn` bilinçli no-op (sahte n-bar outcome
   kirletmesin diye) ama yorum hâlâ kaldırılmış `real_historical_backtest.py`'den
   bahsediyor — yorum/kod driftı.
9. `version.py::SYSTEM_VERSION` (1.53.0) ile `CURRENT_STATE.md` (v1.9x) uyuşmuyor.
10. MetaStage yorumları 0.75/0.90'dan bahsediyor ama gerçek sabitler
    `STRONG_DISSENT_CONFIDENCE_THRESHOLD=0.65` / `BENCHED_..._THRESHOLD=0.70`.

## 🟢 Kontrol ettim, kullanıcının hatırladığından farklı çıktı

11. **"Respond sekmesinde LLM GPT olması lazım ama deepseek-v4-flash yazıyor."**
    Kod kontrol edildi: `llm_reasoner.py::NvidiaDecisionCritic` hâlâ gerçekten
    `deepseek-ai/deepseek-v4-flash-0731` kullanıyor — GPT'ye geçiş kodda YOK.
    Muhtemelen kullanıcı bunu, GPT'ye harici olarak danışılan mimari
    incelemelerle (CURRENT_STATE.md'de sık geçen "harici AI incelemesi/GPT
    raporu" — uygulama İÇİNDEKİ Respond sekmesi değil, kullanıcının kendi
    ChatGPT sohbetleri) karıştırıyor. **Netleştirme gerekiyor**: gerçekten
    Respond sekmesinin modelini NVIDIA'dan OpenAI GPT'ye geçirmek mi istiyorsun
    (yeni API key/config gerektirir), yoksa yanlış hatırlıyor musun?

## 🆕 Yeni özellik/analiz istekleri (henüz kod incelemesi gerekmiyor, tasarım kararı gerekiyor)

12. **Kazanma oranı çöküşü (21-23 Ağustos, ~%85 → %38) için otomatik rejim-
    değişimi tespiti.** `analytics/scientific_self_correction.py` (bugünkü
    taramada bulunan, hiçbir yere wire edilmemiş modül) TAM OLARAK bunun için
    yazılmış — iki-oran z-testiyle bir hipotezin/stratejinin edge'inin zamanla
    kaybolup kaybolmadığını dürüstçe test ediyor. Sıradaki wire-edilecek modül
    adayı olarak öne çıkıyor.
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
16. Settings'teki mum aralığı (candle timeframe) seçimi tek seçime zorluyor —
    kullanıcı 15dk/4s/1g'nin AYRI AYRI değerlendirilip değerlendirilmediğini
    soruyor; eğer zaten öyle çalışıyorsa bu ayar ölü bölge, tartışılmalı.
17. **"Tepeden giriş" hâlâ devam ediyor** (bugünkü XAUTUSDT örneği zaten
    incelendi — ADX zayıfken bile hiçbir sert engel yok). Kullanıcı özellikle
    destek/direnç seviyesi bazlı bir filtre istiyor: kritik seviyeden %X'ten
    fazla uzaktaysa (örn. tepeden/dipten kovalıyorsa) giriş engellensin.
18. Genel: sistem "her fırsatı alıyor," seçicilik eksik — giriş eşiği/kriterleri
    gözden geçirilmeli.
19. "Pozisyon büyütme asla" ilkesi (sadece küçültme) — zaten meta-label/Kelly'de
    kısmen var, ama genel bir mimari ilke olarak dokümante edilip her yeni
    modülde bu kurala uyulduğu doğrulanmalı.
20. Arbitraj pozisyon detay kartı istek listesi: spot/futures bacak, entry/current
    basis, funding earned, fees, unrealized/net PnL, exit condition — Dashboard'a
    yeni bir detay görünümü.
21. Dashboard'a "AI şu an piyasa yönünü nasıl görüyor" bilgi kartı (mevcut
    ortalama/dominant belief.direction'ın canlı özeti).

## Notlar

- Kullanıcı `max_open_positions_per_symbol_direction`'a (1000) bilerek
  dokunmamamızı istedi — test modunda gereksiz kısıtlama. Madde 4 (fiyat bazlı
  kontrol) bundan AYRI, hâlâ geçerli bir istek.
- Faz 353 (`moe_regime_router`) bu turdan önce zaten wire edildi ve commit
  edildi — ayrı.
