# Mevcut Durum -- v1.94.0 (Faz 356: Scientific Self-Correction canlıya bağlandı — council'in isabet oranı yön/deney-kovası bazında otomatik retest ediliyor)

**Tarih:** 2026-08-24
**Branch:** main
**Son commit (HEAD):** Faz 356 (bu commit ile).
**✅ Servis durumu:** Faz 353 (MoE Regime Router) + Faz 354 (dashboard bugları) + Faz 355 (confidence timeline) — uvicorn/celery/beat 24 Ağustos 12:37 UTC'de temiz restart edildi (önceki restart'taki gibi bir tıkanıklık yaşanmadı), hepsi canlıda doğrulandı (/health 200, yeni karar akıyor).

## Faz 356 — Scientific Self-Correction canlıya bağlandı (2026-08-24)

Kullanıcı isteği: "2-3 gündür kazanma oranım düştü... sistem bunu kendi kendine fark edip etiketleyebilsin mi." `analytics/scientific_self_correction.py` (iki-oran z-testiyle bir hipotezin edge'inin zamanla kaybolup kaybolmadığını test eden, hiçbir yere wire edilmemiş modül) için gerçek veriyle önce SORUNUN KENDİSİ doğrulandı: `experiments` tablosu (docstring'in önerdiği doğal tüketici) incelendi, sadece 7 satır (hepsi tek bir geliştirme-zamanı "RSI<30" test kaydı) — anlamlı bir retest kaynağı değil. Bunun yerine `decisions` tablosundan (mae_mfe_confidence_gatherer.py'nin kanıtlanmış deseniyle AYNI) besleniyor.

**Gerçek bulgu (recent_days=3, pump_fade/basis_arb hariç):** genel isabet aslında DÜŞMEMİŞ, İYİLEŞMİŞ (%70.3→%79.0) — ama **LONG özelinde GERÇEK ve istatistiksel olarak anlamlı bir bozulma var** (%96.2→%80.6, p<0.0001, `hypothesis_still_valid=false`, n=977 vs 1136). SHORT değişmemiş (~%22 sabit — kronik kötü, drift değil). Deney kovaları (control/treatment) ayrı ayrı anlamlı değişmemiş. Yani kullanıcının "%85-90'dan %38'e düştü" izlenimi ham rakamla tam örtüşmüyor ama sezgisi (yakın zamanda gerçek bir bozulma var) doğrulandı — SADECE LONG'da, sistem genelinde değil.

**Kod:** `services/scientific_self_correction_gatherer.py::gather_scientific_self_correction()` — overall + yön (LONG/SHORT) + experiment_bucket kırılımlarında retest çalıştırıyor, `research_summary_gatherer.py::_MODULES` registry'sine 14. modül olarak eklendi (mevcut şekil-agnostik "Genel Özet" kartı otomatik gösteriyor, frontend değişikliği gerekmedi — "Detaya git" için ayrı bir sayfa bu turun kapsamı dışında bırakıldı, boş içerik gösterir).

**Test:** 3 yeni entegrasyon testi (gerçek DecisionPersistor.persist/close_position ile — LONG bozulması doğru tespit ediliyor, mekanik stratejiler dışlanıyor, min-sample altında fail-closed boş dönüyor) temiz.

**Not:** entry_timing.py için de daha isabetli bir soru soruldu ("ilk N dakikada belirgin MAE oluşursa nihai sonuç ne olur") — gerçek, monoton bir bulgu çıktı (erken >%5 MAE → %55.6 kazanma vs erken MAE yoksa %99.9) ama bunu WIRE etmek (örn. erken büyük ters harekette stop sıkılaştırma) BACKLOG.md #5'teki kâr-koruma/trailing eksikliğiyle aynı, ayrı bir tasarım kararı — henüz uygulanmadı.

## Faz 355 — Confidence Timeline mimari düzeltmesi (2026-08-23/24)

Kullanıcının 2 günlük gözlem turunda getirdiği harici mimari incelemenin (bkz. BACKLOG.md #3) en yüksek öncelikli maddesi. Kod incelemesiyle bağımsız doğrulandı: `MetaStage` (`engines/cognitive_pipeline.py`) `final_size`'ı ACT/REDUCE dalında `meta["confidence"]`'a göre TEK seferlik hesaplıyor — bir daha yeniden türetilmiyor. `DecisionFusion` confidence'ı kalibre edip EV kapısını KENDİ confidence'ıyla doğru kontrol ediyor (bu kısım zaten sağlamdı). Ama `orchestrator.py::_apply_portfolio_fusion`'daki İKİ portföy-seviyeli indirim (aynı-yönlü korelasyon, düşük Effective-Number-of-Bets) — `CognitiveEngine.run()` TAMAMEN bittikten SONRA çalışıyor, SADECE `ctx.decision.confidence`'ı güncelliyordu, `final_size`'a HİÇ dokunmuyordu (yorum "sadece boyut küçülüyor" diyordu ama gerçekte hiçbir şey küçülmüyordu — sadece explain sayfasındaki gösterilen sayı değişiyordu) VE act_threshold'u asla yeniden kontrol etmiyordu (ACT kararı eski/yüksek confidence'la kalıcı kalıyordu).

**Düzeltme:** İki indirim bloğu artık `final_size`'ı da AYNI oranda küçültüyor, ve yeni `_revert_to_wait_if_below_act_threshold()` — indirim sonrası confidence act_threshold'un altına düşerse kararı dürüstçe WAIT'e çeviriyor (final_size=0). Karar zaten WAIT'e dönmüşse ikinci indirim bloğu (ENB) artık tekrar loglamıyor (gereksiz gürültü önlendi).

**Test:** `tests/test_portfolio_fusion_wiring.py` — 2 yeni test (final_size'ın gerçekten küçüldüğü, act_threshold altına düşünce WAIT'e dönüldüğü) + 4 mevcut testin act_threshold/max_confidence_mode_enabled mock eksikliği düzeltildi ve YENİ (doğru) davranışa göre eşikleri güncellendi (ör. "gevşek VaR'da boyut hiç değişmemeli" → "eski birim hatasındaki ~30'a çökmemeli," artık meşru ENB küçülmesi payı bırakılarak). 12/12 temiz.

**Not:** Bu, harici incelemenin #1/#2 maddesinin SADECE portföy-seviyesindeki yarısı — DecisionFusion'ın kendi kalibrasyonu zaten sağlamdı, dokunulmadı. REDUCE semantiği (madde #6) ve agent-agreement çifte-uygulama (madde #7) ayrı, henüz incelenmedi.
**⚠️ `execution_mode` hâlâ global "simulated"** — testnet kodunun çalıştığı kanıtlandı (Faz 349) ama hiçbir canlı davranış değişmedi.
**⚠️ `max_confidence_mode_enabled=false` (varsayılan)** — Pozisyon Havuzu (Faz 350) inşa edildi ama henüz kullanıcı tarafından açılmadı.
**⚠️ `max_open_positions_per_symbol_direction=1000`** (varsayılan 5, "admin" tarafından 14 Ağustos'ta gevşetilmiş) — kullanıcı bilinçli olarak DEĞİŞTİRİLMEMESİNİ istedi (test modunda kısıtlama gereksiz). XAUTUSDT'de 17 aynı-yönlü pozisyon birikmişti, bu ayar yüzünden — bilerek dokunulmadı.

## Faz 353 — Mixture-of-Experts Regime Router canlıya bağlandı (2026-08-22)

Kullanıcı isteği ("wire edilmeyen modül/ajan var mı, ölçelim hazır olanları wire edelim") ile analytics/ altındaki 11 ölçüm-only modül taranıp gerçek veriyle önceliklendirildi (bkz. proje hafızası — kalan 10 tanesi hâlâ ölçüm-only, sonraki turda değerlendirilecek). `moe_regime_router.py` (Faz 369-393'ten beri hiçbir yere bağlı değildi) günün XAUTUSDT vakasıyla (17 aynı-yönlü LONG, teknik ajan zayıf ADX/OBV ıraksamasına rağmen LONG oyu vermiş, mean-reversion uzmanı quant ajan WAIT demiş ama benched olduğu için oyu sıfırlanmış) doğrudan alakalı bulundu.

**Gerçek OOS kanıtı (4410 kapalı karar, mekanik stratejiler hariç):** mean-reversion rejiminde (hurst≤0.45) technical_agent'la (momentum-flavored) aynı yöne giden kararlar %62.7 isabetli (n=1087) iken quant_agent'la (mean-reversion-flavored) aynı yöne gidenler %84.6 (n=501) — 22 puanlık fark. Trending rejiminde (hurst≥0.55) TERSİ: technical %66.5 (n=197) vs quant %53.1 (n=130). moe_regime_router'ın önerdiği tilt yönüyle İKİ rejimde de tutarlı.

**Kod değişikliği:** `services/council_orchestrator.py::deliberate()` — debate-penalty döngüsünden hemen sonra, `belief_engine.synthesize()`'dan ÖNCE — `contexts[AgentDomain.QUANT].hurst_exponent` okunup `compute_moe_expert_weights()` çağrılıyor, dönen `momentum_weight`/`mean_reversion_weight` çarpanı SADECE `AgentDomain.TECHNICAL` ve `AgentDomain.QUANT` opinion'larının `performance_weight`'ine uygulanıp `recalculate()` ediliyor. MAX_TILT=%30 ile sınırlı (bir uzmanı asla tamamen susturmaz), QUANT context'i hiç yoksa (partial council) fail-closed no-op.

**Test:** 3 yeni entegrasyon testi (`tests/test_council_orchestrator.py` — mean-reversion tilt, trending tilt, QUANT context yokken no-op; technical_agent'ın canlı DB'de gerçekten benched olması testleri etkilemesin diye `reliability_annotator.annotate()` monkeypatch'lendi) + mevcut `test_moe_regime_router.py` (saf fonksiyon testleri, önceden yazılmış ama hiç çağrılmıyordu) + geniş council/orchestrator/belief regresyonu (118 test) — 2 bilinen pre-existing flaky (`test_partial_council`, `test_single_agent_directional_agreement_is_not_flagged_as_crowding`, `git stash` ile doğrulandı: technical_agent canlı DB'de gerçekten benched, değişiklikten bağımsız) hariç temiz.

## Faz 352 — Regime Reversal Guardian: yön-bazlı ardışık stop-loss koruması (2026-08-22)

Kullanıcı fikri, GERÇEK ve o anda yaşanan bir olayla doğrulandı: "piyasa her an dönüş yapabilir, bir yönde art arda pozisyonlar stop olmaya başlarsa sistem yön değişikliği konusunda şüphelenmeye başlamalı." Canlıda: LONG'da art arda 14 stop-loss (birbirinden bağımsız birçok sembolde, ~2 saatlik bir pencerede), aynı anda 275 açık LONG'un 170'i zararda — kullanıcı onayıyla 107 kârdaki LONG elle kapatıldı (+$1566.70 kilitlendi). Bu modül aynı tepkiyi kalıcı/otomatik hale getiriyor.

İki parça: (1) **Ölçüm** — `analytics/regime_reversal.py::consecutive_stop_streak()` (saf fonksiyon) + `services/regime_reversal_guardian.py::compute_direction_stop_streaks()` bir yönün (LONG/SHORT) son kapanışlarında ardışık stop-loss sayısını hesaplar; kill switch'in GLOBAL sayacının (services/risk_state.py) yön-bazlı hali. Mekanik stratejiler (pump_fade_v1/basis_arb_v1) hariç — kendi risk yönetimlerine sahipler, streak'e karışırsa yanlış alarm üretebilir. Stateless: hiçbir "duraklatıldı" bayrağı persiste edilmiyor, bir kazanç gelince streak kendiliğinden sıfırlanır. (2) **Aksiyon** — SADECE ikisi: (a) `regime_reversal_guardian_task` (60sn'de bir, Celery beat) eşiği aşan yöndeki KÂRDAKİ açık pozisyonları tazeden fiyatla defansif kapatır (`/positions/close-profitable` ile AYNI mantık, tek yöne filtrelenmiş). (b) `MetaStage`'e eklenen gate (Faz 342'nin bearish_low SHORT gate'iyle AYNI desen) eşiği aşan yönde yeni pozisyon açılmasını WAIT'e zorluyor.

Yeni ayarlar: `reversal_guardian_enabled` (varsayılan **true** — kill switch gibi koruyucu bir mekanizma, alfa üreten deneysel bir modül değil), `reversal_guardian_consecutive_stop_threshold` (varsayılan 5 — gerçek geçmiş dağılımla kalibre edildi: LONG streak'leri normalde 1-4, SHORT çok daha oynak; 5 hem gerçek olayı (14) rahat yakalıyor hem gürültü seviyesinde tetiklenmiyor). Dashboard Settings'e karşılık gelen kart eklendi.

**Test:** 17 yeni test (`test_regime_reversal.py`, `test_regime_reversal_guardian.py`, `test_meta_stage_regime_reversal_gate.py`) + ilgili geniş regresyon (61 test) temiz.

**Ayrıca bu turda:** proje genelinde import sıralaması otomatik düzeltmesi (isort/ruff) — davranış değişikliği yok, sadece stil.

## Faz 351 — Meta-Label Model'e agent_agreement özelliği eklendi: gerçek OOS iyileşmesi (2026-08-22)

Kullanıcı isteği ("2000+ kapanmış işlem var, wire edecek modül yok mu?") ile ölçüm-only modüller yeniden tarandı. `analytics/opportunity_quality.py` (Faz 569-593'ten beri hiçbir gate'e bağlı değildi) gerçek 1998 kapanmış işlemde çarpıcı bir sonuç verdi: ajan konsensüsü (LONG/SHORT/WAIT oylarının entropi-tabanlı anlaşma skoru) "medium" kovada %92.4 win_rate (n=590) vs "low" kovada %68.5 (n=1401) — örtüşmeyen %95 güven aralıkları, gerçek ve büyük bir etki.

Bunu AYRI bir gate/tablo olarak wire etmek yerine (çakışma/çifte-sayım riski), zaten canlıya bağlı (Faz 348) Meta-Label Model'e BİR özellik olarak eklendi — aynı, zaten onaylı mimari. `analytics/opportunity_quality.py`'ye paylaşılan iki saf fonksiyon eklendi: `agreement_from_contributions()` (eğitim, geçmiş `agent_contributions`'tan) ve `agreement_from_opinions()` (canlı, `RiskTargetStage`'e artık iletilen `opinions` listesinden) — ikisi AYNI entropi formülünü kullanıyor, train/predict tutarsızlığı riski yok.

**Gerçek OOS kanıtı (retrain, n=882, aynı örneklem büyüklüğü):** test_accuracy %85.2 → **%90.2**, test_auc 0.93 → **0.957**, baseline_correctness_rate %69.8 (hâlâ soundly geçiliyor). Model gerçekten eğitilip kaydedildi (canlıda aktif).

**Kod değişikliği:** `RiskTargetStage.execute(ctx, opinions=None)` — imza değişti, `services/cognitive_engine.py::run()` artık `opinions`'ı iletiyor. Geriye dönük uyumlu (opinions verilmezse agent_agreement fail-closed 0.0).

**Test:** 4 yeni test (`test_opportunity_quality.py` +4, `test_meta_label_model.py` +1, `test_risk_target_stage.py` +2) + 200+ mevcut ilgili test (decision_recorder/cognitive_binding/e2e/backtest/red_team/tp_sl_confluence vb.) temiz.

## Faz 350 — KRİTİK: sistem saatlerce hiç pozisyon açmıyordu (MISSING_LIMIT) + Pozisyon Havuzu / Max Confidence Modu inşa edildi (2026-08-22)

**Kesinti (kullanıcı bulgusu: "2.000 den fazla kapanan pozisyon var ama 300 kalmış, sistem pozisyon almıyor"):** Kök neden `risk_limits` tablosunda `max_position_size` satırının TAMAMEN eksik olmasıydı — `RiskEngine` her cycle'da `MISSING_LIMIT` ile fail-closed reddediyordu, bu da `GuardrailStage`'in council'ı HİÇ ÇAĞIRMADAN (agent'lara hiç sorulmadan) confidence=0.0/WAIT üretmesine yol açıyordu (~14.000 ardışık WAIT, gerçek ajan hatası YOK — pipeline en baştan kesiliyordu). Ayrıca `max_capital_pct`/`max_concurrent_positions` ayarları önceki bir oturumda saçma değerlere (1000000/100000) çekilmiş bulundu — muhtemelen aynı sorunu bypass etmeye çalışan bir geçmiş müdahale. Düzeltme: `max_position_size=$200k` risk_limits'e eklendi; `max_capital_pct`/`max_concurrent_positions` mevcut 320 pozisyonluk birikimi karşılayacak (%500/500) sağlıklı değerlere çekildi; `starting_capital` zaten kullanıcının istediği 500k'daydı. Canlı doğrulama: `risk_verdict=approved` dönüyor, agent'lar tekrar çağrılıyor.

**Ayrıca:** `api/rest/agents.py`'deki `_DESCRIPTIONS` sözlüğü Faz 333/336'da eklenen Credit/Volatility ajanlarıyla hiç güncellenmemiş kalmıştı (Agents sayfasında boş açıklama) — eklendi.

**Pozisyon Havuzu / Max Confidence Modu (kullanıcı fikri, 2026-08-21 onaylandı):** council'ın normal (deneysel bucket'sız) yolunda risk-onaylı bir karar hemen açılmak yerine `max_confidence_mode_pool_window_minutes` (varsayılan 15dk) boyunca yeni `position_pool_candidates` tablosunda birikir; periyodik görev (`resolve_position_pool_task`, 60sn'de bir kontrol) penceresi kapanmış adayları confidence'a göre sıralayıp sadece `max_confidence_mode_top_k` (varsayılan 3) tanesini GERÇEK, TAZE fiyattan (pool anındaki DEĞİL) `pump_fade_strategy.py`/`basis_arbitrage_strategy.py` ile AYNI "council pipeline'ını atlayan direkt DecisionPersistor" deseniyle açar; geri kalanı "rejected" işaretlenir. Seçim anında hafif bir risk-headroom kontrolü var (ai_enabled/max_concurrent/max_capital_pct hâlâ uygun mu) — uygun değilse "failed". Varsayılan KAPALI, `decisions.status`'a YENİ bir değer eklemiyor (ayrı tablo — mevcut status-tabanlı sorguların kirlenmesi riski yok). `services/decision_recorder.py`'ye tek bir kontrol noktası eklendi (entry_price hesaplandıktan hemen sonra, deneysel bucket'sız + risk-onaylı açılışlarda).

**Test:** 9 yeni test (`tests/test_position_pool.py`) + 54 mevcut ilgili test (decision_recorder/execution_mode/app_settings_api/celery_tasks) temiz. Migration hem `quantdb` hem `quantdb_test`'e uygulandı.

## Faz 349 — Binance Algo Order API migrasyonu: GERÇEK testnet doğrulamasında bulundu (2026-08-21)

Kullanıcı onayıyla yapılan gerçek uçtan uca testnet doğrulamasında (bilinçli, kontrollü, minimum boyutlu — BTCUSDT, ~$70 notional) kritik bir bug bulundu: giriş MARKET emri başarıyla doldu ama koruma emirleri (STOP_MARKET/TAKE_PROFIT_MARKET) Binance'den **-4120 "Order type not supported for this endpoint"** hatası aldı. Sistemin kendi güvenlik mekanizması (çıplak pozisyon asla ilkesi) bunu yakalayıp pozisyonu otomatik acil kapattı — DOĞRU çalıştı, ama asıl hedef (başarılı uçtan uca açılış) başarısız oldu.

**Kök neden (WebSearch ile doğrulandı):** Binance 2025-12-09'da koşullu emirleri (STOP_MARKET/TAKE_PROFIT_MARKET dahil) eski `POST /fapi/v1/order`'dan YENİ bir Algo Order servisine taşıdı — kırıcı bir API değişikliği, freqtrade/nautilus_trader gibi başka bot projelerinde de AYNI hatayla doğrulandı. Bu kod Faz 315'te (bu değişiklikten ÖNCE) yazılmıştı — mock'lu testler eski API sözleşmesini varsaydığı için hiç yakalamadı. **Bu, gerçek uçtan uca doğrulamanın NEDEN gerekli olduğunun kanıtı.**

`exchange_gateway/binance/futures_execution_adapter.py` düzeltildi: STOP_MARKET/TAKE_PROFIT_MARKET artık `POST /fapi/v1/algoOrder`'a yönleniyor (`triggerPrice`/`clientAlgoId`/`algoType=CONDITIONAL` — Binance'in Algo API'sinin KENDİ parametre isimleri), `get_order_status`/`cancel_order` önce normal endpoint'i dener sonra sessizce algo'ya düşer, `_parse_algo_order_status` gerçek dolumu (`actualQty>0`) mevcut sistemin beklediği "FILLED" statüsüne çeviriyor.

**Düzeltmeden SONRA gerçek doğrulama:** BTCUSDT'de gerçek LONG pozisyon açıldı, GERÇEK STOP_MARKET+TAKE_PROFIT_MARKET koruma emirleri yerleşti (borsadan bağımsız sorgularla doğrulandı), sonra temiz kapatıldı — testnet hesabında hiçbir kalıntı yok.

**Test:** 1 test yeni şemaya güncellendi, 3 yeni test eklendi. İlgili execution suite'i (47 test) temiz.
**⚠️ `basis_arbitrage_enabled=false` (varsayılan)** — Faz 344 henüz hiçbir gerçek pozisyon açmıyor, kullanıcı Settings'ten açıkça açmadan devreye girmez.
**⚠️ OPERASYONEL DERS (2026-08-21):** Faz 344'ün hata ayıklaması sırasında pytest DIŞINDA çalıştırılan ham `.venv/bin/python -c` debug scriptleri `conftest.py`'nin `quantdb_test` yönlendirmesini atlayıp GERÇEK `quantdb`'e 5 sahte pozisyon yazdı — kullanıcı Transactions'ta fark edip sordu, kaynağı bulunup onayla silindi. Kalıcı kural [[feedback_debug_scripts_must_target_test_db]] hafızasına eklendi.

## Faz 348 — Meta-Label Model canlı karara bağlandı: sadece pozisyon boyutu çarpanı (2026-08-21)

Kullanıcı isteği (1752 kapanmış işlemle "modüllere bakıp wire edelim"): `services/meta_label_model.py` (Faz 268-sonrası'ndan beri eğitiliyordu ama hiçbir canlı karara bağlanmıyordu) gerçek OOS kanıtı ölçülüp kullanıcıya gösterildi — test_accuracy %85.2 (taban oranı %61.4), test_auc 0.93, n=878 — önceden belirlenmiş "taban oranını gerçekten yenerse bağlanabilir" çizgisini net geçti. Adaptive Barrier Engine de kontrol edildi, zaten aktifti.

Kullanıcı onayıyla (netleştirme sorusu): SADECE pozisyon boyutu çarpanı olarak bağlandı (Kelly boyutlandırmayla AYNI "sadece küçült, asla büyütme" ilkesi) — yön kararı hiç etkilenmiyor. `RiskTargetStage` — stop/target set edildikten HEMEN SONRA (MetaStage'in aksine bu aşamada planned_rr_ratio hesaplanabiliyor) `predict_tp_probability` çağrılıyor, `meta_label_size_multiplier` ile final_size sadece küçültülüyor. Henüz model yoksa (fail-closed None) hiçbir şey değişmez. Yeni `retrain_meta_label_model_task` (günlük) — gerçek model hemen eğitilip kaydedildi, canlıda doğrulandı.

**Test:** 6 yeni test, geniş council/orchestrator/e2e/pairs_trader regresyonu (47+ test) temiz.

## Faz 347 — /positions'a kısa süreli (8sn) görüntüleme fiyat önbelleği (2026-08-21)

Kullanıcı bulgusu: "sistem genel olarak hantal/yavaş çalışıyor." Kök neden: GET /positions (Dashboard + Transactions'ın ikisi de kullanıyor) 66 benzersiz sembolde ~9sn sürüyordu — Binance hız sınırlayıcısı (saniyede 15 istek) TÜM süreçler arasında paylaşılıyor, dashboard yükleme/15sn'lik yenileme canlı trading döngüsüyle AYNI bütçeyi paylaşıp çakışıyordu. Sadece GÖRÜNTÜLEME amaçlı 8sn'lik süreç-içi önbellek eklendi — `services/position_closer.py::fetch_current_prices_by_symbol`'e (stop/hedef/likidasyon kontrolü, güvenlik kritik) KASITLI bulaşmadı. Ölçüldü: 2.35s → 0.0s (sıcak çağrı).

## Faz 346 — Autonomous Strategy Synthesizer v1: Regime Gate Discovery (2026-08-21)

Kullanıcı vizyonu ("belirli koşullar birlikteyken hafızaya bakıp tanısın") — netleştirme sorusuyla v1 kapsamı onaylandı: bugün elle yapılan sürecin (SHORT/bearish_low bulgusu, Faz 342) OTOMASYONU, yeni açık-uçlu strateji mantığı icat eden bir sistem DEĞİL. CMA-ES ajan ayarının (`meta_optimizer/agent_tuner.py`, Faz 239-241) "ölç → OOS kanıtla → insan onayı" zincirinin genellenmiş hali.

`analytics/strategy_hypothesis_scanner.py::scan_for_gate_candidates()` — strategy×regime uzayını tarar, bir hücrenin win_rate'i AYNI stratejinin GERİ KALANINDAN (hücre HARİÇ — kontaminasyon önlenir, gerçek bulgu: bir hücre kendi stratejisinin ÇOĞUNLUĞU olduğunda kirletilmiş delta_vs_overall gerçek etkiyi gizliyordu, düzeltildi) istatistiksel olarak anlamlı kötüyse aday işaretler; onlarca hücre aynı anda test edildiği için Benjamini-Hochberg FDR düzeltmesi (`causal_inference.py`, Faz 331) uygulanıyor. `validate_candidate_out_of_sample()` — aday, zaman sırasına göre ikiye bölünüp (embargo boşluklu) hiç görülmemiş geç yarıda da aynı yönde kötü çıkıyor mu test ediyor.

Kasıtlı olarak SADECE ölçüm/aday üretimi — hiçbir aday otomatik bir gate'e bağlanmıyor. Gerçek doğrulama: SHORT/bearish_low/swing (Faz 342'nin zaten kapattığı kombinasyon) tek aday olarak bulundu (n=403, delta=-%32.5, p≈0) — ama zaman-bölünmüş OOS testinde henüz tekrarlanmadı (bearish_low'un yakın zamana yoğunlaşması nedeniyle) — sistem abartmadan dürüstçe bunu da raporluyor.

**Test:** 8 yeni test (gerçek enjekte edilmiş etki tespiti, FDR gürültü filtreleme, OOS tekrarlanma/tekrarlanmama, kontaminasyon önleme dahil).

## Faz 345 — strategy_regime_compatibility'ye trade_type (scalp/swing) kırılımı (2026-08-21)

Kullanıcı vizyonu ("Scalp %99 başarılı bu koşullarda, örüntüyü tanıyabilirse büyük olay") için gerçekçi, kanıtlanabilir ilk adım — "joint örüntü tanıma" hedefinin küçültülmüş, istatistiksel olarak savunulabilir hali. Tam 9-ajan kombinasyon uzayı (2⁹=512 hücre) ~1600 işlemle aşırı uydurmaya açık (`agent_combination_reliability.py` bu yüzden bilerek ikiliyle sınırlı) — bunun yerine council etiketine trade_type (scalp/swing, `positions.py::_classify_trade_type` ile AYNI %4.5 eşik) eklenip uzay ~50-60 hücreye indirildi.

**Canlı doğrulama çarpıcı:** SHORT/bearish_low'un (Faz 342'de WAIT'e zorlanan kombinasyon) içinde bile scalp (%66.7, n=21) ile swing (%5.2, n=403) arasında devasa fark var — swing SHORT asıl sorunun ana kaynağı. LONG/bearish_low/scalp ise %100 (n=299). `basis_arb_v1` artık kendi ayrı temel etiketini alıyor (önceden yanlışlıkla "ai_council"a düşüyordu). Hâlâ ölçüm-only, hiçbir gate'e bağlı değil.

**Test:** 7 yeni test (13 toplam, gerçek entegrasyon dahil).

## Faz 344 — Cross-Asset Arbitrage Engine v1: spot-perpetual basis arbitrajı (2026-08-21)

Kullanıcı onayı: ikinci dalga ajan/motor planının ilk maddesi. Klasik, piyasa-nötr cash-and-carry: perpetual futures spot'a göre PRİMLİ işlem görürken (pozitif basis) VE funding rate pozitifken SHORT perpetual + LONG spot açılır. `market_data/basis/binance_futures_provider.py` — Binance'in genel, key'siz `/fapi/v1/premiumIndex` uç noktasından gerçek mark/index price + funding rate (gerçek 875 perpetual sembolde ölçüldü: |basis| medyanı %0.058, p90 %0.267 — eşikler buna göre kalibre edildi). `services/basis_arbitrage_strategy.py` — pump_fade/pairs_trader ile AYNI desen (council'den izole, kendi `basis_arb_v1` experiment_bucket'ı).

**Kritik tasarım kararı:** iki bacak AYNI varlıkta (pairs_trader'ın FARKLI varlıklarının aksine) — biri bağımsız ATR stop/hedefle kapanırsa kalan bacak çıplak yönlü bir pozisyon olur. Bacaklar standart `PositionCloser` taramasından GEÇMİYOR (stop/target hiç set edilmiyor) — ayrı bir Celery task (`close_due_basis_arbitrage_pairs_task`, dakikada bir) sadece maksimum tutma süresi (varsayılan 72s) dolunca ikisini BİRLİKTE kapatıyor.

**Geliştirme sırasında bulunan/düzeltilen 2 gerçek mimari hata:**
1. RiskEngine'in aynı-sembol cooldown'u (`min_seconds_between_trades`, varsayılan 60sn) iki bacağı arka arkaya açmayı GERÇEKTEN engelliyordu (test değil, canlıda da olurdu) — risk durumu artık her iki bacak için de BİR KEZ, hiçbir bacak açılmadan ÖNCEki durumu yansıtacak şekilde okunuyor.
2. `DecisionRecorder.record()`'a `experiment_bucket` hiç geçilmiyordu — pozisyonlar deneysel etiketsiz kalıyordu.

Transactions'a "Basis Arb" rozeti + filtre eklendi (pump_fade'in "Transactions'ta göremiyorum" sorununu tekrarlamamak için).

**Test:** `tests/test_basis_arbitrage_strategy.py` (11 yeni, YALNIZ bir bacağın asla tek başına kapatılmaması güvenlik testi dahil), geniş regresyon (pairs_trader/pump_fade/settings_api/celery_tasks/position_closer, 145+ test) temiz.

**Sıradaki (kullanıcı sırası):** MempoolAgent ya da BehavioralAgent (veri kaynağı kısıtları nedeniyle henüz kapsam netleşmedi, bkz. proje hafızası).

## Faz 343 — Harici GPT mimari eleştirisinin kalan maddeleri incelendi (2026-08-21)

Faz 342'de council'in SHORT/bearish_low sorununu çözdükten sonra, GPT raporunun kalan 4 maddesi gerçek veriyle tek tek test edildi:

1. **TP/SL Confluence "LONG target=%0"**: BUG DEĞİL. Gerçek 14 günlük BTCUSDT düşüş penceresi (22 Oca-5 Şub 2026, -%29.8) simüle edildi — o dönemde confluence dağılımı tersine dönüyor (çoğu seviye fiyatın üstünde, mevcut yükseliş ölçümünün tam tersi). Rejim artefaktı, `services/tp_sl_confluence_gatherer.py`'ye bulgu notu eklendi.
2. **Macro "dominance"**: tersi doğru çıktı. SHORT/bearish_low'daki 424 işlemin TAMAMINDA (%100) Macro LONG oy vermiş (isabet %91.6) — Technical (%99.5 SHORT) + Pattern (%64 SHORT) + Quant (Faz 339 öncesi) Macro'nun doğru sesini ezmiş. Faz 342'nin gate'i bunu zaten düzeltiyor.
3. **Technical'ın "içsel tutarsız" IC'leri**: regime confound (Simpson paradoksu). `bollinger_confirm` mimari olarak SADECE `trend=="bearish"` iken ateşleniyor — kötü IC'si (-0.54) SADECE bearish_low'dan geliyor, dışarıda anlamsız (p=0.35). En zararlı hali Faz 342'yle zaten nötrlenmiş — RSI/OBV/trend regime'ler arası tutarlı, büyük bir "Technical'ı böl" refactor'u ŞU AN gerekmiyor.
4. **N tutarsızlığı**: bug değil, kasıtlı farklı popülasyonlar — her modül zaten kendi N'ini raporluyor.

Sonuç: dördü de ya bug-değil-artefakt ya da zaten Faz 342 ile çözülmüş çıktı — sadece #1'in bulgu notu kod değişikliği gerektirdi. Market World Model'in yeniden çerçevelenmesi (kozmetik) düşük öncelikte backlog'da kaldı.

**Sıradaki (kullanıcı sırası):** İkinci dalga ajanlar (MempoolAgent, BehavioralAgent, Cross-Asset Arbitrage).

## Faz 342 — Council'in SHORT/bearish_low kombinasyonu WAIT'e zorlanıyor (2026-08-21)

Kullanıcı isteği: "short pozisyonlar neden karlı değil?" Harici bir AI incelemesinin (rakamları gerçek sistemden birebir doğrulandı) `bearish_low` bulgusunu council'in kendi SHORT/LONG kararlarına yön kırılımıyla test ettim. Gerçek 1577 kapanmış kararla ölçüldü: council'in SHORT kararları genel %21.6 isabetli (LONG %96.4) — ama TEK bir rejimden kaynaklanıyor. `market_regime` kırılımı: SHORT/bearish/low n=424, isabet SADECE %8.3 (toplam -$604); LONG/bearish/low n=398, isabet %95.2 (+$141). Diğer bearish alt-rejimlerinde SHORT çok daha iyi (normal %46.8 n=47, high %90.9 n=11).

Kök neden: `market_regime` = TechnicalContext'in HIZLI EMA20/EMA50 kesişimine (`trend`) + gerçekleşen volatiliteye dayanıyor — QuantAgent'ın (Faz 339'da düzeltilen) yavaş 200-EMA'sından FARKLI bir sinyal. "bearish_low" (EMA20<EMA50 + düşük volatilite) fiilen bir düşüş devamı değil, klasik bir taban/konsolidasyon kurulumu — SHORT açmak dönüşe karşı bahis oluyor. pump_fade'in Faz 327/332/341'de zaten düzelttiği "bearish ≠ SHORT-favorable" hatasının council seviyesindeki karşılığı.

`engines/cognitive_pipeline.py::MetaStage` — sideways_market gate'inin hemen ardına, AYNI desende yeni bir gate: SADECE `belief.direction=="SHORT" and trend=="bearish" and volatility_regime=="low"` iken `meta["decision"]="WAIT"`. LONG'a, diğer rejimlere dokunulmuyor — "sadece sıkılaştır" ilkesi.

Bu arada Transactions'ın karda/zararda kartına (Faz 340) kullanıcı isteğiyle renk ayrımı eklendi (karda=yeşil, zararda=kırmızı, tek renk yerine).

**Test:** `tests/test_meta_stage_bearish_low_short_gate.py` (5 yeni), geniş MetaStage/council regresyonu (29 test) temiz. `test_pairs_trader.py`'nin 2 bilinen pre-existing flaky testi (`git stash` ile doğrulandı, değişiklikten bağımsız) hariç geniş entegrasyon paketi (26 test) temiz.

**Sıradaki (kullanıcı sırası):** Faz 338'in strategy_regime_compatibility'sine YÖN (LONG/SHORT) kırılımı eklemek — GPT'nin en önemli iddiasının genel, tüm stratejiler için ölçüm hali.

## Faz 341 — pump_fade stop-sonrası tekrar giriş sıkılaştırması (2026-08-21)

Kullanıcı bulgusu: bir sembolde pump_fade stop olduktan SONRA pump devam ettiği için normal `pump_fade_min_gain_pct` (%15) hâlâ geçiliyordu — sistem bir sonraki döngüde AYNI sembolde tekrar SHORT açıp tekrar stop oluyordu. Kullanıcı isteği: "stop olduktan sonra tekrar girecekse fiyat %20 değil %50 yükselirse tekrar girsin."

Yeni `pump_fade_reentry_min_gain_pct` ayarı (varsayılan 0.50). `DecisionPersistor.symbols_with_last_exit_reason_stop_loss()` (DISTINCT ON, her sembolün EN SON kapanışı) `run_cycle()`'da adayları filtreliyor: bir sembolün son kapanan pump_fade işlemi stop_loss ise, o döngüde `gain_pct` normal eşiği geçse bile daha sıkı reentry eşiğini de geçmeli, geçmezse aday elenir. `find_pump_candidates`'in genel `min_gain_pct`'i değişmedi (tüm ilk-girişler için kalibre kalıyor) — bu sadece tekrar-giriş için ek bir kapı. Settings.tsx'e karşılık gelen ayar kartı eklendi.

**Test:** `tests/test_pump_fade_strategy.py`'ye 3 yeni test (persistor metodunun DISTINCT ON semantiği + run_cycle'ın hem engelleme hem izin verme dalları) — 44 pump_fade testi temiz. Bu arada `tests/test_app_settings_api.py`'de Faz 332'de kaldırılan `pump_fade_capital_pct`'ye referans veren, hep `KeyError` ile başarısız olan bir kalıntı da düzeltildi (`pump_fade_max_total_capital_pct` ile değiştirildi, ayrıca yeni ayarın validasyonu da eklendi).

## Faz 340 — Transactions: açık pozisyon karda/zararda yüzde kartı (2026-08-21)

Kullanıcı isteği: açık pozisyonların yüzde kaçının karda yüzde kaçının zararda olduğunu gösteren bir kart. TÜM açık pozisyonlar üzerinden olmalı (sadece görüntülenen sayfa değil) — ama gerçek ölçüm: 747 açık pozisyon/134 benzersiz sembolde tam bir tarama ~15-30 saniye sürüyor (paralel fiyat çekme + varsa finansman maliyeti). İstek anında hesaplamak Faz 268w'nin düzelttiği "Transactions çok yavaş açılıyor" sorununu geri getirirdi.

Çözüm: yeni `refresh_open_position_pnl_summary_task` (dakikada bir, `close_due_positions_task` ile AYNI cadence ama AYRI kilit) arka planda hesaplayıp `app_settings`'e yazıyor (`open_positions_profit_count`/`open_positions_loss_count`); API sadece okuyor (~0.02s, DB round-trip dışında maliyet yok). Komisyon/finansman maliyeti kasıtlı DIŞARIDA (`gross_unrealized_pnl` — sadece fiyat farkı) — dashboard'daki diğer kaba kâr/zarar filtreleriyle aynı basitlik seviyesinde, kesin kuruşluk bir rakam değil. `fetch_current_prices_by_symbol`/`gross_unrealized_pnl` paylaşılan kullanım için `api/rest/positions.py`'den `services/position_closer.py`'ye taşındı.

**Test:** İlgili 9 test dosyası (position_closer/positions/celery_tasks) çalıştırıldı — 1 bilinen flaky test (`test_position_close_feeds_agent_learning.py`, `git stash` ile doğrulandı, paylaşılan test-DB durumu kaynaklı, koddan bağımsız) hariç temiz. Manuel: task gerçek 747 pozisyon/134 sembolde çalıştırılıp (508 karda, 238 zararda) sonuç `app_settings`'te doğrulandı, API okuma 0.025s ölçüldü.

## Faz 339 — QuantAgent'tan long_term_trend_regime TAMAMEN kaldırıldı (2026-08-21)

Kullanıcı bulgusu: "quant ajanın son 20 tahmininde isabet %0-5, CI %0-16." Faz 317'nin confidence-indirim bandaid'i (agree durumunda ×0.6) yetersiz kaldığı doğrulandı. Kök nedene inildi: son 3000 kapanmış kararda quant'ın 489 LONG/SHORT oyu TEK kanıt kaynağına göre ayrıştırıldı — `long_term_trend_regime` (yavaş/gecikmeli 200-EMA) TEK BAŞINA ateşlendiğinde (oyların %65'i, n=319): **%15.7 isabet** (yazı-turadan kötü). Gerçek Hurst/z-score/otokorelasyon sinyali ateşlendiğinde (n=17, oyların sadece %3.5'i): **%76.5 isabet** (küçük örneklem ama %50 şansla açıklanamayacak kadar iyi, ~p<0.03).

Kullanıcı: "sistemde tutmanın anlamı yok, ya geliştirelim işe yarasın ya da atalım." Üç seçenek sunuldu (kötü bileşeni kes/çekirdeği koru, ajanı tamamen kaldır, dokunma-gözle) — kullanıcı "kötü bileşeni kes" seçti. `long_term_trend_regime` ve `regime_changepoint_detected` — hem `agents/quant_agent.py::analyze()`'den (long_term_trend_regime skorlama bloğu + changepoint indirimi + Faz 317 trend-uyum confidence indirimi, `_TREND_AGREEMENT_CONFIDENCE_DISCOUNT` dahil), hem `contracts/quant.py::QuantContext`'ten, hem `services/context_adapter.py::to_quant()`'tan TAMAMEN silindi (QuantContext'in tek kullanıcısı quant_agent olduğu doğrulandı — başka hiçbir yerde referans yok). Ajan artık SADECE kendi gerçek istatistiksel çekirdeğine (Hurst rejimi + z-score mean-reversion + otokorelasyon momentum) dayanıyor — çok daha seyrek ama gerçek kenarlı oy veriyor, çoğu zaman WAIT.

Not: `long_term_trend_regime` HAM özniteliği (`market_data/features/signal_engine.py::compute_quant_signals()`) sistemden silinmedi — pump_fade'in rejim gate'i ve feature registry hâlâ kullanıyor, sadece QuantAgent'ın ondan beslenmesi kesildi.

**Test:** `tests/test_quant_agent.py` yeniden yazıldı (9 test, kaldırılan mantığa bağlı 8 test silindi/birleştirildi), `tests/test_context_adapter_new_domains.py`'den 2 ilgisiz kalan test silindi. Geniş council regresyonu (175 test) — 3 bilinen pre-existing flaky (`test_council_orchestrator.py`, `git stash` ile doğrulandı, değişiklikten bağımsız) hariç temiz.

## Faz 338 — Strateji × Rejim Uyumu / MetaStrategyAgent v1 (2026-08-21)

Kullanıcı sorusu: "Sistem hangi senaryoda hangi strateji başarılı diye ölçüyor mu acaba? Şu an uyguladığı scalp stratejisi long'da çok başarılı ama piyasa bearish olduğu zaman çok başarısız olacak belki." Yanıt: HAYIR, ölçmüyordu — `decisions.market_regime` (Faz 244-246'dan beri kapanışta yazılıyor) hiçbir yerde okunup toplu raporlanmıyordu. pump_fade'in bugünkü felaketiyle (bullish rejimde SHORT-only strateji hâlâ tam boyutta işlem açıyordu) TAM olarak aynı desenin genel, tüm stratejiler için tekrarlanabilir hali — harici bir AI incelemesinin de bağımsız önerdiği modül.

`analytics/strategy_regime_compatibility.py::compute_strategy_regime_compatibility()` — GERÇEK kapanmış kararları `strategy × market_regime`'e göre gruplayıp her kovanın win_rate'ini, %95 güven aralığını ve stratejinin KENDİ genel win_rate'ine göre farkını (`delta_vs_overall`) hesaplıyor; `min_group_size=15` altındaki kovalar fail-closed dışlanıyor. `services/strategy_regime_compatibility_gatherer.py` gerçek `decisions` tablosundan (son 5000, `status='closed' AND market_regime IS NOT NULL`) besliyor; `experiment_bucket`'a göre `"pump_fade"` / `"ai_council"` etiketliyor (v1'de kasıtlı kaba ayrım). `api/rest/strategy_regime_compatibility.py` tek canlı `GET /` endpoint'i (Self-Model'in en basit deseniyle aynı — haftalık snapshot/repository/migration KATMANI bilinçli olarak v1 kapsamı dışında bırakıldı, sadece ölçüm).

Kasıtlı olarak SADECE ölçüm/rapor — v1'de hiçbir gate'e otomatik bağlı değil, hiçbir stratejiyi ALLOW/REDUCE/BLOCK etmiyor ("yeni meta-model = ölçüm-only, hemen güvenli; karara bağlamak = ayrı OOS kanıtı + onay gerektirir" ilkesi). Dashboard'a "Strateji × Rejim Uyumu" sayfası + Sidebar girişi + "Genel Özet" panelindeki 12. modül olarak eklendi.

**Test:** `tests/test_strategy_regime_compatibility.py` (5 yeni, pure-function), `api/main.py` route kaydı `TestClient` ile doğrulandı (401 dönüyor, 404 değil), dashboard `tsc --noEmit` temiz.

## Faz 337 — Execution Impact Estimator: pump_fade'e ölçüm-only bağlandı (2026-08-21)

Harici bir AI incelemesinin önerisi: gerçek emirler gönderilmeden önce bile, mevcut `order_book_snapshots` (Faz 186, sadece top-of-book) verisiyle beklenen piyasa etkisini/kayma maliyetini TAHMİN edip kayda geçirmek — henüz hiçbir boyutlandırma kararını otomatik küçültmüyor (o, ayrı bir onay gerektirir; execution_mode="testnet" plan Faz 1'in kapsamı).

`services/execution_impact_estimator.py::estimate_execution_cost_pct()` — Kyle (1985)/Almgren-Chriss (2000) kare-kök piyasa etkisi yaklaşımı: `impact_pct = half_spread_pct × sqrt(notional/available_liquidity)`; order book yoksa `None` döner (fail-closed, uydurma değer yok). `pump_fade_strategy.py::_try_open` her pozisyon açılışında bu tahmini hesaplayıp `agent_opinions`'a `execution_cost_estimate` girdisi olarak LOG-ONLY ekliyor.

**Test:** `tests/test_execution_impact_estimator.py` (7 yeni, pure-function), `test_pump_fade_strategy.py`'ye 1 yeni entegrasyon testi (gerçek `order_book_snapshots` satırı seed edilip opinion'ın göründüğü doğrulanıyor) — pump_fade toplam 41 test.

## Faz 336 — Volatility Agent: 11. oy-veren ajan eklendi (2026-08-21)

Kullanıcının onayladığı ikinci dalga ajan listesinden (Mempool, Execution, Volatility, Credit) sıradaki. Deribit'in genel/anahtarsız API'sinden gerçek DVOL (kripto VIX) verisi: `market_data/volatility/deribit_provider.py::fetch_dvol_level/fetch_dvol_trend` (15dk cache; 24 saatte >%15 yükseliş "spiking", >%15 düşüş "falling", aksi "stable"). `agents/volatility_agent.py::VolatilityAgent` — asimetrik: spiking → SHORT -1.0 (volatilite patlaması genelde risk-off/tepe sinyali), falling → LONG +0.5 (daha zayıf, "sakinleşme" tek başına güçlü bir yön sinyali değil), stable → katkı yok. `AgentDomain.VOLATILITY` + `VOTING_AGENT_DOMAINS`'e eklendi, council artık 11 ajanlı.

**Test:** `tests/test_volatility_agent.py` (7 yeni).

## Faz 335 — NUPL/SOPR OnChainAgent'a bağlandı (2026-08-21)

Kullanıcı bulgusu: "İstediğim [on-chain] metrikler sisteme entegre edilmemiş hatta todo listesinden silinmiş." Doğrulandı: `fetch_nupl`/`fetch_sopr`/`fetch_realized_price`/`fetch_mayer_multiple`/`fetch_total2_total3_market_cap_usd`/`fetch_stablecoin_dominance_vs_eth_pct` (Faz 316-sonrası'nda yazılıp bitcoin-data.com'a karşı test edilmişti) `market_data/onchain/onchain_provider.py`'de duruyordu ama HİÇBİRİ `contracts/onchain.py::OnChainContext`'e, `agents/onchain_agent.py`'ye ya da `services/context_adapter.py`'ye hiç bağlanmamıştı — sadece kendi test dosyalarından çağrılıyorlardı, karar hattına sıfır katkıları vardı.

Bu turda NUPL (Net Unrealized Profit/Loss, >0.75 "euphoria"/tarihsel tepe, <0 "capitulation"/tarihsel dip) ve SOPR (Spent Output Profit Ratio, <0.98 zararla satış/kapitülasyon, >1.05 kârla satış/sağlıklı yükseliş) MVRV Z-Score ile AYNI desende (bitcoin-data.com, genel piyasa koşulu, TÜM kripto sembollerine uygulanıyor — network_activity_trend/hash_rate_trend'in aksine BTC'ye özel değil) `OnChainAgent`'a bağlandı. `fetch_realized_price`/`fetch_mayer_multiple` BİLİNÇLİ OLARAK bağlanmadı — mevcut MVRV Z-Score/`long_term_trend_regime` (200-EMA) ile kavramsal olarak örtüşüyorlar, ekstra sinyal değeri şüpheli; `fetch_total2_total3`/`fetch_stablecoin_dominance_vs_eth` de kapsam dışı bırakıldı (henüz net bir kullanım senaryosu yok).

**Test:** `tests/test_onchain_agent.py` (+6 yeni test: NUPL/SOPR uç değerleri, nötr bölge katkı vermiyor, None fail-closed), broader onchain regresyonu (74 test) temiz. Canlı doğrulama bitcoin-data.com'un saatlik ücretsiz kota limitine (429) takıldı ama bu, fail-closed mekanizmanın (veri yoksa hiçbir katkı üretilmiyor, uydurma sinyal yok) doğru çalıştığını GERÇEK bir ağ hatasıyla kanıtladı — fetch fonksiyonlarının kendisi zaten önceden gerçek veriyle doğrulanmıştı.

**Ayrıca bu segmentte (Faz 334, önceden commitlendi):** `scripts/service_watchdog.sh` — stop_loss aşma bug'ının (%27 işlem gerçek stop seviyesini aşarak kapanıyordu) kök nedeni bulundu: kod hatası değil, bu ortamda uvicorn/celery'yi hiçbir process supervisor izlemiyordu (ZROUSDT örneği: fiyat stop'u geçtikten 30 SAAT sonra kapandı). Watchdog 60sn'de bir sağlık kontrolü yapıp düşerse otomatik restart ediyor — gerçek production'daki K8s liveness probe'un (Faz 180) yerel karşılığı.

## Faz 333 — Credit Agent: 10. oy-veren ajan eklendi (2026-08-21)

Kullanıcı isteği: harici bir AI incelemesinin önerdiği yeni ajan/motor listesinden (Volatility/Credit/SupplyChain/Mempool/Behavioral/Execution/Quantum/Adversarial vb.) gerçekçi/ucuz olanlar ("Mempool, Execution, Volatility, Credit bunları mutlaka ekleyelim, birer birer aktifleştiririz") onaylandı — Quantum/Adversarial/SupplyChain/Federated Learning pratik değil ya da erken bulunup bilinçli olarak ertelendi (bkz. `project_open_items_2026_08_21.md` hafıza kaydı). "Credit leads equity" ilkesiyle sıralamada ilk: en ucuz/hazır (FRED zaten entegre, Faz 197).

İki gerçek, resmi, kesin tanımlı FRED serisi (MacroAgent'ın `net_liquidity_trend`'iyle AYNI desen): `T10Y2Y` (10Y-2Y Hazine getiri farkı, "yield curve" — negatifse tersine dönmüş, tarihsel en köklü resesyon uyarı sinyallerinden biri) ve `BAMLH0A0HYM2` (ICE BofA ABD Yüksek Getirili Endeks OAS — genişliyorsa kredi koşulları sıkılaşıyor/risk-off, daralıyorsa risk-on). `market_data/macro/fred_provider.py::fetch_yield_curve_signal/fetch_credit_spread_trend`, `contracts/credit.py::CreditContext`, `agents/credit_agent.py::CreditAgent` (yield curve asimetrik puanlanıyor — SADECE inversiyon cezalandırılıyor, "normal" durum ödüllendirilmiyor; credit spread simetrik — MacroAgent'ın liquidity_condition'ıyla aynı), `services/context_adapter.py::to_credit()`, `AgentDomain.CREDIT` + `VOTING_AGENT_DOMAINS`'e eklendi, `agents/registry.py`/`engines/cognitive_pipeline.py`'ye wire edildi.

Yeni bir sinyal, henüz bu sistemde gerçek kapanmış işlemlerle doğrulanmadı — ama SourceReliabilityAgent'ın zaten var olan otomatik-bench mekanizması (kötü performans gösteren domain'lerin effective_influence'ını otomatik sıfırlayan sistem, eski SENTIMENT ajanını böyle elemişti) zayıf çıkarsa doğal olarak süzecek.

**Test:** `tests/test_credit_agent.py` (6 yeni), `tests/test_nine_agent_council.py` + council/context-adapter regresyonu (68 test, 3 bilinen pre-existing flaky hariç) temiz.

**Sıradaki (kullanıcı sıralaması):** stop_loss aşma bug'ı → on-chain metrikler → VolatilityAgent → MempoolAgent → ExecutionAgent → uçtan uca testnet doğrulaması (en sona).

## Faz 332 — pump_fade KÖK NEDEN düzeltmesi: risk-bazlı boyutlandırma + pozisyon-sayı tavanı + zarar devre kesici + rejim gate'i güçlendirildi (2026-08-21)

**Gerçek olay (kritik, kullanıcı canlıda yakaladı):** kasa %17 ROI'den ~%2'ye düştü. Kök neden bulundu: **82 açık pump_fade pozisyonu, toplam GERÇEKLEŞMEMİŞ zarar -$453.648** (anlık piyasa fiyatlarıyla ölçüldü, $500K başlangıç sermayesinin neredeyse tamamı). Kazanma oranı aslında iyiydi (%75.6, n=156) — sorun isabet değil, boyutlandırmaydı: eski formül (`margin = starting_capital × pump_fade_capital_pct(0.05)`, stop mesafesinden BAĞIMSIZ sabit $25.000) `pump_fade_stop_distance_pct=%30` (sabit, geniş) ile birleşince tek pozisyonda ~$16.500 kayıp riski taşıyordu. Kullanıcı: "sağlam çözüm bulmamız lazım öyle basit çözümlerle geçiştiremeyiz."

Harici bir AI incelemesi (GPT) danışıldı, sıralama üzerinde tartışıldı — kullanıcı onayıyla nihai sıra: (3) pozisyon-sayı tavanı, (1) risk-bazlı boyutlandırma, (2) zarar-bazlı devre kesici, + rejim gate'i sıkılaştırma. Korelasyon-kümesi (BTC-beta/L1/memecoin ayrımı) fikri BİLİNÇLİ OLARAK reddedildi — pump_fade zaten SADECE SHORT açıyor (tüm pozisyonları zaten %100 yön-korelasyonlu), zarar devre kesici bu riski yeterince basit şekilde yakalıyor.

**1) Risk-bazlı boyutlandırma (`pump_fade_max_loss_per_trade_usd`, varsayılan $500).** Eski `pump_fade_capital_pct` TAMAMEN kaldırıldı. Margin artık "stop'a takılırsa TAM OLARAK bu kadar $ kaybedilsin" eşitliğinden GERİYE hesaplanıyor: `margin = max_loss_per_trade_usd / (stop_distance_pct × kaldıraç)` — AI council'in Kelly-bazlı sabit-$-risk felsefesiyle AYNI ilke, GPT'nin önerdiği formülle matematiksel olarak birebir aynı. Eski $25.000'lık margin'i ~$750'ye indiriyor (stop=%30, kaldıraç~2.2x'te).

**2) Pozisyon-sayı tavanı (`pump_fade_max_open_positions`, varsayılan 20).** Kümülatif MARJİN tavanı (Faz 330) tek başına yetersizdi — risk-bazlı boyutlandırma sonrası tek pozisyon marjini küçüldüğü için tavana ÇOK DAHA FAZLA pozisyon sığar hale geldi (82-99 pozisyon aynı anda, çoğunlukla AYNI yönde). Yeni `DecisionPersistor.count_open_positions_for_experiment()`.

**3) Zarar-bazlı devre kesici (`pump_fade_max_loss_circuit_breaker_usd`, varsayılan $10.000).** Mevcut kümülatif marjin tavanı sadece "ne kadar sermaye BAĞLANABİLİR"i sınırlıyordu, "ne kadar KAYBEDİLEBİLİR"i sınırlamıyordu. `run_cycle()` her tetiklenişte önce `DecisionPersistor.total_pnl_for_experiment()` (SADECE gerçekleşmiş/kapanmış pnl) kontrol ediyor — eşiği aşarsa `pump_fade_enabled` OTOMATİK `false` olur, `EventLogRepository`'ye KRİTİK olay yazılır. Matematik güzel örtüşüyor: 20 pozisyon × $500 = $10.000 — en kötü eşzamanlı senaryoda bile devre kesici hemen tetiklenir, toplam olası zarar artık ~$10-20K'da (eskiden sınırsız, ~$453K'ya kadar) tavanlanıyor.

**4) Rejim gate'i güçlendirildi (`_compute_regime_size_multiplier`).** Gerçek veriyle ölçüldü: son 48 saatte gate'in kapsadığı 43 açılıştan 22'si (%51) hâlâ 1.0x (indirimsiz) çıkmıştı — BTC açıkça yükseliş trendindeyken bile. İki bağımsız kök neden bulundu ve düzeltildi: (a) BTC'nin bull_trend rejimi eskiden council_bull_bias (AI'nın kendi açık pozisyonlarının O ANKİ, gürültülü kâr/zarar anlık görüntüsü) True dönmeden hiç kontrol edilmiyordu — artık BTC bull_trend TAMAMEN BAĞIMSIZ, kendi başına yeterli bir sinyal (PARTIAL_FLOOR); council bias da doğrularsa en sıkı tabana (FLOOR) düşülüyor. (b) CANLI durumda yakalandı: BTC 5 günde ~%20 sıçramıştı ($64.532→$77.410) ama 200-EMA hâlâ "transition" diyordu (yapısal gecikme) VE açık AI SHORT sayısı (2) min. örneklem eşiğinin (5) altındaydı — LONG'ların %94.7'si (n=38) kârdayken bile çarpan 1.0 kalıyordu. Yeni `_REGIME_GATE_LONG_ONLY_STRONG_SIGNAL_MIN=0.90`: SHORT örneklemi yetersizken LONG tarafı TEK BAŞINA yeterince büyük VE ezici bir örneklemse (SHORT örneklemi YETERLİYSE bu dal bilerek devre dışı, gerçek gap'in kendisi daha güvenilir) bağımsız bir bull sinyali sayılıyor. Canlı doğrulama: düzeltme öncesi 1.0, sonrası 0.5 (PARTIAL_FLOOR).

**Ayrıca bu turda:** `pump_fade_enabled=false` yapıldı (kullanıcı onayıyla, mevcut 82 pozisyona DOKUNULMADI — kullanıcı kararı: "kendi stop'larına bırakalım"), ResearchSummary.tsx'in kompakt özetleyicisi düzeltildi (primitif dizi/dict alanları artık içerik gösteriyor, sadece sayı değil — Self-Model'in "degraded" nedeni artık görünür).

**Test:** `tests/test_pump_fade_strategy.py` — 40 test (11 yeni: pozisyon-sayı tavanı ×2, devre kesici ×2, repository metodları ×2, rejim gate ×3, mevcut testlerin yeni formüle göre düzeltilmesi). Toplam hedefli regresyon 74 test, hepsi temiz.

**Ayrı, henüz araştırılmamış bulgular (todo'ya eklendi, unutulmasın):**
- Sistem genelinde son 7 günde "stop_loss" ile kapanan 810 işlemden 216'sı (%27) gerçek stop seviyesini aşarak (en kötü %12) kapanmış — muhtemelen bayat/gecikmeli fiyat verisi, kök neden henüz bulunmadı.
- AI council'in KENDİ (pump_fade dışı) SHORT kararları %21.7 isabetli (LONG %96.4) — pump_fade'den bağımsız, ayrı bir mimari sorun.
- Kullanıcının istediği on-chain metrikler entegre edilmemiş, hatta todo listesinden silinmiş görünüyor — henüz araştırılmadı.
- 8 yeni ajan/motor fikri (Volatility/Credit/Execution/Mempool grounded; Quantum/Adversarial/SupplyChain/Federated pratik değil ya da erken) — kullanıcı sıcak bakıyor ama BİLİNÇLİ OLARAK ertelendi: önce bugün pump_fade'e kurulan governance modelinin (eligibility gate + risk-bazlı sizing + circuit breaker) haftalarca canlıda kanıtlanması gerekiyor.
- Uçtan uca gerçek testnet doğrulaması (Execution Layer) hâlâ yapılmadı — anahtarlar çalışıyor, tek sembolde gerçek emir denenmedi.

## Faz 331 — Agent Combination Reliability (yeni Grup B modülü) + Causal Inference'a FDR düzeltmesi (2026-08-21)

Kullanıcı, harici bir GPT incelemesinin (Genel Özet panelini okuyup yazdığı uzun bir rapor) önerdiği maddelerden ikisini onayladı: "kolay olanlar" (Brier yeniden ölçüm + FDR düzeltmesi) ve — birden fazla kez ertelenmiş, kullanıcının ısrarla "es geçmeyelim" dediği — **ajan-kombinasyonu koşullu güvenilirliği**. Council mimarisinin kendisini yeniden tasarlama önerisi (rapor madde 2) kullanıcı onayıyla "ileride" olarak bırakıldı.

**1) Causal Inference — Benjamini-Hochberg FDR düzeltmesi.** Kök sorun: BTC/ETH × 47 varlık ~96 çift AYNI ANDA bağımsız α=0.05 ile test ediliyordu — gerçek ilişki hiç olmasa bile şans eseri ~5 "anlamlı" sonuç beklenir (multiple testing). `analytics/causal_inference.py::apply_fdr_correction()` (yeni, statsmodels.stats.multitest.multipletests) eklendi; `services/causal_inference_gatherer.py` artık TÜM test edilen çiftlerin p-value'sını toplayıp tek seferde FDR uyguluyor. Geriye dönük uyumluluk: `significant_relationships` (ham p<0.05) davranışı DEĞİŞMEDİ, her satıra ek `fdr_significant` bayrağı + ayrı `fdr_significant_relationships` listesi eklendi. Dashboard (`CausalInference.tsx`) yeni "FDR sonrası" sütunu gösteriyor.

**2) Agent Combination Reliability — YENİ Grup B modülü.** Opportunity Quality (Faz 569-593) council'de KAÇ ajanın anlaştığını (Shannon entropi) win_rate ile ilişkilendiriyordu — bu modül HANGİ ajan İKİLİLERİNİN birlikte anlaştığını ilişkilendiriyor. Neden ikili (36 çift, C(9,2)) ve tam altküme (2^9=512) değil: örneklem (~1400) altkümede hücre başına anlamsızca küçülür, aşırı uydurma riski yüksek olurdu — causal_inference.py'nin çift-bazlı test deseniyle AYNI ilke. `analytics/agent_combination_reliability.py` (saf: `agreeing_domains_for_decision` — agent_ablation.py'nin `reconstruct_opinions`'ını yeniden kullanıyor; `compute_pairwise_combination_reliability` — her ikili için "her ikisi de nihai yönle aynı yönde oy verdi" kovasının win_rate'ini genel ortalamayla karşılaştırıyor, iki-oranlı z-testi + AYNI FDR düzeltmesiyle). `services/agent_combination_reliability_gatherer.py` (gerçek veri, pump_fade_v1 hariç — Opportunity Quality/Agent Ablation ile AYNI dışlama). Tam stack: contract (`contracts/agent_combination_reliability_report.py`), migration (`faz331`, hem quantdb hem quantdb_test'e uygulandı), repository, `GET /agent-combination-reliability/` + `/reports`, haftalık celery task (`refresh_agent_combination_reliability_report_task`), `AgentCombinationReliability.tsx` (Sidebar → Research), `research_summary_gatherer.py::_MODULES`'e eklendi (artık 11 modül).

**Gerçek, canlı sonuç (1416 işlem, pump_fade hariç, genel ortalama %71.6):** `macro` domain'i HER üst sırada — macro+quant n=35 %100, macro+technical n=390 %98.0, macro+sentiment n=309 %96.1, macro+order_flow n=243 %95.5, macro+pattern n=314 %94.9 — hepsi baseline'ın 22-28 puan üstünde ve FDR'ı geçiyor. Bu, aynı GPT raporunun BAĞIMSIZ bir bulgusuyla (Direction Prediction'da Macro'nun en düşük/en iyi Brier skoruna sahip olduğu, 0.152/n=831) doğrudan örtüşüyor — iki ayrı ölçüm yöntemi aynı sonuca işaret ediyor.

**Test:** `tests/test_agent_combination_reliability.py` (7, saf fonksiyonlar — FDR'ın gerçek edge'i koruyup gürültüyü elediği dahil), `tests/test_agent_combination_reliability_wiring.py` (5, API+task+repo uçtan uca), `tests/test_causal_inference.py`/`_wiring.py` (FDR eklentisiyle güncellendi), `tests/test_research_summary.py` (11 modül, hardcoded "10" kaldırıldı, dinamik `len(_MODULES)`'e geçirildi) — toplam 47+ test, hepsi temiz.

**Ayrıca bu segmentte (Faz 329/330, önceden commitlendi):** `Decision.stop_loss/take_profit` → `stop_loss_distance/take_profit_distance` (Kimi'nin bulduğu adlandırma tuzağı, davranış değişmedi); pump_fade'in kümülatif sermaye tavanı yokmuş — "sadece kripto alıyor" görüntüsünün asıl sebebi ana council döngüsünün `MAX_CAPITAL_PCT` kapısında %915-980 okunan (kaldıraçlı notional/marjin karışıklığı + pump_fade'in tavansız büyümesi) kilitlenme imiş; `pump_fade_max_total_capital_pct` yeni ayarı (varsayılan %20) eklendi. Binance Futures Testnet API anahtarları alındı, doğrulandı ($5000 sanal bakiye).

## Faz 330 — "Sistem sadece kripto alıyor" araştırması -> pump_fade'in kümülatif sermaye tavanı yokmuş, ana council döngüsü tamamen kilitlenmiş (2026-08-20)

Kullanıcı isteği (daha önceki bir turdan bilerek ertelenmişti): "Sistemin aldığı işlemler hep kripto işlemleri diğer varlıklarla işlem yapmayı durdurmuş gibi görünüyor bunun nedenini araştıralım." Gerçek DB sorgularıyla araştırıldı, gözlem doğruydu ama sebep "kripto vs diğer" değildi:

**Kök neden**: `GuardrailStage`'in `MAX_CAPITAL_PCT` kapısı (%100 tavan) `capital_used_pct`'i **%915-980** okuyordu, bu yüzden ana council döngüsünün önerdiği HER şeyi (BTCUSDT dahil — kripto majors + hisse/emtia, varlık sınıfı fark etmeksizin) daha council çalışmadan reddediyordu. `pump_fade_strategy.py` ise bu global kapıdan hiç geçmiyor (kendi izole sermaye mantığı) — tek çalışan strateji o kaldığı ve sadece geniş bir kripto USDT-perpetual evrenini taradığı için "sistem sadece kripto alıyor" görüntüsü oluştu. Kanıt: son 2 saatte açılan pozisyonların 32'si pump_fade, 6'sı ana döngü.

**İki ayrı, gerçek bug bulundu ve düzeltildi:**

1. **`services/risk_state.py::load_position_risk_state`** — `capital_committed = Σ(entry_price×quantity)` idi, ama `quantity` zaten `decision_recorder.py`'de kaldıraçla çarpılmış — yani bu NOTIONAL'dı, gerçek marjin değil. Artık `/leverage` ile bölünüyor (leverage None/0 ise kaldıraçsız varsayılır). Düzeltilmiş rakam bile ~%443 çıktı — sorunun asıl kaynağı #2.

2. **`services/pump_fade_strategy.py::_try_open`** — hiçbir kümülatif kontrol yoktu, her yeni işlem SADECE kendi boyutuna (`pump_fade_capital_pct`, %5) bakıyordu, o an kaç pozisyon zaten açık olduğuna hiç bakmıyordu. Gerçek veride: 99 açık pump_fade pozisyonu, toplam gerçek marjin $2.21M (~%443 sermaye, 99×%5≈%495 ile örtüşüyor). Yeni `DecisionPersistor.total_open_margin_for_experiment(bucket)` (SQL SUM, notional/leverage) + yeni ayar **`pump_fade_max_total_capital_pct`** (varsayılan %20, kullanıcı isteğiyle Settings sayfasına da eklendi) — her yeni işlem açılmadan önce (zaten açık toplam marjin + bu işlemin marjini) bu tavanı aşıyorsa işlem hiç açılmıyor. "Sinyal limitleri gevşetemez, sadece küçültebilir" ilkesiyle aynı desen, artık kümülatif seviyede de uygulanıyor.

**Test**: `tests/test_pump_fade_strategy.py` (+4 yeni test: kümülatif tavan reddi, tavan içindeyken serbest açılış, `total_open_margin_for_experiment` leverage-bölme doğruluğu, mevcut 24 test hâlâ geçiyor — `_set_pump_fade_settings` yardımcı fonksiyonuna paylaşılan-test-DB-kirlenmesi için bol bir varsayılan tavan eklendi, `test_pairs_trader.py`'deki `max_capital_pct="1000000"` deseniyle aynı), `tests/test_risk_state.py` (+1 yeni test: leverage-bölünmüş marjin doğruluğu). Toplam hedefli regresyon: 148 test temiz.

**Ayrıca bu turda (aynı segment, önceki maddeler):** Faz 329 — Kimi'nin bulduğu `stop_loss`/`take_profit` alan adlandırma tuzağı düzeltildi: `contracts/contexts/decision.py`'deki `Decision.stop_loss`/`take_profit` (aslında entry_price'a göre MESAFE/magnitüd, mutlak fiyat değil) `stop_loss_distance`/`take_profit_distance` olarak yeniden adlandırıldı — canlı bir bug değildi (tüm mevcut kullanımlar zaten doğru yorumluyordu), sadece isim netleştirildi, 7 üretim dosyası + ilgili testler güncellendi, 114 test temiz (2 önceden var olan, alakasız `test_pairs_trader.py` flakiness'i hariç). Binance Futures Testnet API anahtarları alındı ve doğrulandı ($5000 sanal bakiye, `HTTP 200`), `.env`'e `BINANCE_FUTURES_TESTNET_API_KEY/SECRET` olarak kaydedildi (Execution Layer Faz 1'in adaptör/servis/test kodu zaten önceki bir Faz'da — commit `71d4bd5` — tamamlanmış ve commitlenmiş bulundu, sadece anahtar eksikti).

## Faz 328 — Opportunity Quality (Grup B) canlıya bağlandı + kritik confidence write-back bulgusu (2026-08-20)

Kullanıcı onayı: "Opurtunity Quality yi wire edebilirsin önce sonra bakarsın sorun değil." Gerçek veriyle ölçülen (1410 gerçek kapanmış işlem, pump_fade hariç) council ajan-anlaşma kovaları — "low" (agreement<0.34) n=1033 %64.0 kazanma, "medium" n=370 %93.0, "high" n=7 (istatistiksel olarak yetersiz, dokunulmadı, quant_agent'ın "disagree" kovasıyla aynı ilke). `services/decision_fusion.py::DecisionFusion.evaluate()`'e yeni opsiyonel `opinions` parametresi eklendi (CouncilStage'in ürettiği 9 ajan oyu) — SADECE "low" kova, gerçek ölçülen orana göre (%64.0/%93.0≈0.6883) confidence'ı indiriyor. `engines/cognitive_pipeline.py::DecisionFusionStage.execute()` ve `services/cognitive_engine.py::CognitiveEngine.run()` çağrı zinciri `opinions`'ı taşıyacak şekilde güncellendi (council_stage'den zaten scope'ta olan `opinions` değişkeni kullanıldı).

**Kritik, bağımsız bulgu (test yazarken ortaya çıktı):** `DecisionFusion.evaluate()` içinde hesaplanan `confidence` (kalibrasyon eğrisi + cap-tier ayrımı + InnerCritic çarpanı + şimdi opportunity-quality indirimi dahil TÜM ayarlamalardan sonraki hali) hiçbir zaman `ctx.decision.confidence`'a GERİ YAZILMIYORDU — sadece yerel EV hesabında (ENTER/WAIT kapısı) kullanılıp atılıyordu. Bu, Faz 248'in orijinal kalibrasyonundan beri (muhtemelen aylardır) `decisions.confidence` sütununa, dashboard'a ve confidence'a bakan diğer tüketicilere hep HAM/kalibre-edilmemiş değerin gittiği anlamına geliyor — EV kapısı doğru çalışıyordu (doğru yerel değişkeni kullanıyordu), ama dışarıya yansıyan confidence yanlıştı. Düzeltme: `evaluate()`'de InnerCritic çarpanından hemen sonra, EV hesabından önce `ctx.decision.confidence = round(confidence, 4)` eklendi — artık hem EV kapısı hem dışarı yansıyan değer aynı, tam ayarlanmış confidence'ı kullanıyor.
**Test:** `tests/test_opportunity_quality_wiring.py` (yeni, 3 test) + hedefli regresyon (`test_confidence_calibration.py`, `test_risk_target_stage.py`, `test_red_team.py`, `test_inner_critic_wiring.py`, `test_decision_fusion_rejection_persisted.py`, `test_pump_fade_strategy.py`) — 96 passed.

## Faz 326 — "Genel Özet" araştırma paneli (2026-08-20)

Kullanıcı isteği: 10 Grup B (ölçüm-only) araştırma modülünü (Self-Model, Causal Inference, Market World Model, MAE/MFE Confidence, Opportunity Quality, Collective Intelligence, Agent Ablation, Meta-Learning Effectiveness, Direction Prediction V2, TP/SL Confluence) tek tek dolaşmak yerine tek düğmeyle özetleyebilmek — detaylar kendi sayfalarında kalıyor. `services/research_summary_gatherer.py::gather_research_summary()` — kullanıcı kararıyla CANLI hesaplama (her modülün kendi `gather_*()` fonksiyonu), 10'u SIRAYLA değil `ThreadPoolExecutor` ile PARALEL (ölçüldü: ~111 saniye — bazı modüller tüm watchlist'i tarıyor). Bir modülün hatası diğer 9'unu engellemiyor (fail-closed, her zaman 10 kayıt döner). `GET /api/v1/research-summary/`, yeni `ResearchSummary.tsx` (Sidebar → Research → "Genel Özet") — şekil-agnostik bir özetleyici (sample_size/win_rate içeren alt-kovaları otomatik yakalıyor), "Detaya git" ile ilgili sayfaya atlıyor.

Ayrıca: Transactions.tsx'te "scalp" rozeti de "swing" gibi (Faz 322) neutral kaldığı için sönük görünüyordu — yeni bir renk eklenmedi, "orta_vadeli" (Faz 323'te kaldırıldı) sayesinde boşa çıkan `accent` tonuna taşındı.

Bu oturumda ayrıca (özet panelinden önce): Grup A (TP/SL Confluence 7-yöntemli canlı bağlantı) TAMAMLANDI onayı; Grup B modüllerinin veri-yeterlilik taraması yapıldı (Opportunity Quality en güçlü aday: orta-uyum kovası n=368, %92.9 kazanma — kullanıcı "wire edelim" dedi, henüz yapılmadı); pump_fade rejim gate'ine kademeli 2. seviye eklendi (Faz 327, commit 37079d7); scalp min_stop_pct incelendi (empirik optimum %2.46 bulundu) ama kullanıcı kararıyla DOKUNULMADI ("aktif ve başarılıysa değiştirmeyelim").
**Test:** yeni kalibrasyon testlerine + DecisionFusion/RedTeam/InnerCritic'e dokunan hedefli regresyon (82 test) temiz.
**Altyapı notu (2026-08-20):** Docker Desktop bu oturumda bir kez çöktü (postgres/redis konteynerleri durdu) — `docker start` ile geri getirildi, veri kaybı yok.

## Faz 325 — kripto içi büyük-cap/küçük-cap confidence kalibrasyon ayrımı (2026-08-20)

Kullanıcının uzun süredir izlemede tuttuğu madde ("confidence_calibration.py tek 'crypto' kovası") gerçek veriyle ölçüldü ve gerçek, önemli bir bulgu çıktı: `DecisionFusion`'ın EV kapısının kullandığı tek küresel kalibrasyon eğrisinde (`compute_calibration_curve`), confidence=0.4 kovasında büyük-cap kazanma oranı **%77.7** (n=139) iken küçük-cap sadece **%42.5** (n=106) — 35 puanlık gerçek fark, küçük örneklemden değil. Tek eğri bu ikisini harmanlayıp small-cap kararları olduğundan çok daha güvenilir gösteriyordu (EV kapısını yanlışlıkla geçirme riski).

`services/agent_memory.py::crypto_cap_tier(symbol)` — 16 bilinen büyük-cap coin'in elle seçilmiş, açıklanabilir listesi (piyasa değeri API'sine bağlı değil, henüz wire edilmedi). `services/confidence_calibration.py::compute_market_cap_tier_calibration_curves()` — `compute_calibration_curve()` ile AYNI SQL/kesim/kova mantığı, ek olarak tier'a ayrılmış. `get_calibration_curve_for_symbol(symbol)` — `calibrate_domain_confidence`'ın asset-class fallback deseniyle AYNI: tier için yeterli veri varsa ona, yoksa (fail-closed) mevcut tek küresel eğriye düşer. `DecisionFusion.evaluate()` artık `ctx.market.symbol`'ü bu fonksiyona geçiriyor — eski davranış (global eğri) hiçbir zaman bozulmuyor, sadece yeterli veri olduğunda daha keskin bir tahmine geçiliyor.

## Faz 324 — Test stratejisi: property-based testler (hypothesis) + gerçek bir Kelly bug'ı bulundu (2026-08-20)

Kullanıcı isteği: "test stratejisi: contract/chaos/property-based testler." `hypothesis` dev bağımlılığı olarak eklendi. Bu oturum boyunca tekrarlanan "AI kendi risk tavanını genişletemez, sadece daraltabilir" ilkesinin sayısal temelini oluşturan 3 pure fonksiyon grubuna, şu ana kadar SADECE elle seçilmiş örneklerle test edilmiş invaryantları geniş/rastgele girdi uzayında (`tests/property/`, 17 test) sınayan testler eklendi:

1. `analytics/tp_sl_confluence.py::snap_stop_to_confluence/snap_target_to_confluence` — "hangi zone seçilirse seçilsin sonuç asla ham ATR-tabanlı mesafeden daha UZAK olamaz" invaryantı.
2. `simulator/margin.py::max_safe_leverage` — Faz 260'ın gerçek olayının (likidasyon stop'tan ÖNCE tetikleniyordu) kendisi: "max_safe_leverage'in önerdiği kaldıraçla likidasyon HER ZAMAN stop'tan uzakta kalır."
3. `risk/predictive/cppi.py::cppi_exposure_multiplier` + `services/kelly_sizing.py::kelly_fraction` — çarpanların sınırların [MIN,1.0]/[0,1] dışına asla taşmadığı + CPPI'nin risk arttıkça monoton azaldığı.

**Gerçek bulgu:** `kelly_fraction`'ın property testi, `avg_win` denormal derecede küçük bir float (ör. 5e-324) olduğunda `payoff_ratio`'nun float underflow ile tam 0.0'a yuvarlanıp `ZeroDivisionError` fırlattığını buldu — `avg_win <= 0` kontrolü bunu yakalamıyordu çünkü 5e-324 teknik olarak pozitif. Gerçek veride pratik olarak imkansız bir aralık ama gerçek bir crash riskiydi; `payoff_ratio <= 0` kontrolü eklenerek AYNI fail-closed 0.0'a düşürüldü. Property-based testin ilk uygulamasında hemen gerçek bir bug bulması, bu test stratejisinin somut kanıtı.

**Kapsam dışı bırakılan (bilinçli):** "Contract" testleri (`tests/contract/test_llm_explainer.py`) ve "chaos" testleri (`tests/test_red_team.py`: flash_crash/whipsaw_chop/correlated_crash) zaten mevcut/kurulu desenler — bu oturumda genişletilmedi, mevcut kapsamları yeterli bulundu.

## Faz 323 — "orta_vadeli" trade-type kaldırıldı + "Strateji getirisi" kartı düzeltildi (2026-08-20)

Kullanıcı bulgusu: "swing 6 gündür yeni işlem almıyor" + "scalp %100 başarılı görünüyor, mantıksız." Kök neden bulundu: `_classify_trade_type()` `timeframe IN ('4h','1d')` ise diğer her şeyden ÖNCE "orta_vadeli" döndürüyordu — ama `decisions.timeframe`, risk profiliyle değil `candle_timeframe` ayarının karar anındaki değeriyle ilgili, kırılgan bir alan. İki gerçek kaynağı vardı: (1) ~1016 işlem gerçek bir A/B deneyinden (`multi_timeframe_cascade_v1`, `services/orchestrator.py::run_portfolio_aware_cycle`) — "control" kolu bile normal `propose()` ile AYNI mekanizma, sadece deney etiketi taşıyordu; (2) ~108 işlem `candle_timeframe`'in 2026-08-14→08-20 arası yanlışlıkla 4h/1d'de kalmasından (Faz316'da bulunan/düzeltilen AYNI ayar sorunu, audit_log'da doğrulandı: admin 08-14 14:54 değiştirmiş, 08-20 14:45 düzeltilmiş) — scalp/swing'i tam 6 gün boyunca hiç yeni kayıt almadan dondurmuştu. Her iki kaynak da gerçek stop mesafesine göre incelendiğinde doğal bir scalp/swing dağılımı gösteriyordu (control: ort. %1.13 dar / %9.80 geniş) — "orta_vadeli" hiçbir zaman risk-profili temelli bir kategori olmamış, sadece hangi mekanizmanın kararı verdiğiyle ilgiliymiş, ki bu zaten `experiment_bucket`/`services/ab_testing.py` üzerinden ayrı takip ediliyor.

Kullanıcı kararıyla: "orta_vadeli" TAMAMEN kaldırıldı (`api/rest/positions.py::_classify_trade_type`, `database/repositories/decision_persistor.py::_breakdown_by_trade_type` SQL CASE'i, `Transactions.tsx::tradeTypeBadge`, `Dashboard.tsx::TRADE_TYPE_LABELS/ORDER`) — artık HER işlem (deneyler dahil) SADECE gerçek stop mesafesine göre scalp/swing'e ayrılıyor, `candle_timeframe` gibi ilgisiz ayarlara karşı tamamen bağışık. `target_atr_mult_long/short` (Faz 321) ayarları etkilenmedi — yöne göre çalışıyorlar, trade-type etiketinden bağımsız.

Ayrıca kullanıcı bulgusu: "Strateji getirisi" kartı `roi_pct_on_deployed` (tüm-zamanlar hacmine göre getiri, %2.65) gösteriyordu — kasa 500k'dan 574k'ya (gerçek +%14.86) çıkmışken bu "başarısız" gibi görünen, yanıltıcı bir sayıydı. Kart artık gerçek kasa büyümesini (`roi_pct`) gösteriyor, hacim-bazlı oran ikincil bir açıklama metnine taşındı.

## Faz 322 — Dashboard'a LONG/SHORT kazanma oranı kartı + Transactions "Swing" rozetine kendi rengi (2026-08-20)

Kullanıcı isteği: "genel toplamda long short kazanma oranı kartı." `DecisionPersistor.closed_trades_summary_by_direction()` (yeni) — `closed_trades_summary()` ile AYNI kapsam (status='closed', excluded_from_stats=false, pump_fade DAHİL — mevcut "Kazanma oranı" kartıyla tutarlı), direction'a göre gruplu win/loss sayısı. `GET /api/v1/performance`'a `by_direction` alanı eklendi, Dashboard'a iki yeni kart ("LONG kazanma oranı"/"SHORT kazanma oranı", n kazandı/n kaybetti alt-yazısıyla). Gerçek veriyle doğrulandı: **LONG 876 işlem %95.9 kazanma, SHORT 583 işlem %35.2 kazanma** — bu oturumda tekrar tekrar çıkan LONG/SHORT asimetri bulgusunun (R:R kalibrasyonu, pump_fade rejim gate'i) en çıplak/özet hâli.

Ayrıca: Transactions.tsx'te "Swing" rozeti "Scalp" ile aynı `neutral` tonu paylaştığı için sönük görünüyordu (kullanıcı bulgusu) — palet bilinçli olarak minimal tutulduğundan (index.css'teki tasarım notu: "tek bir güvenli accent... rainbow of status colors değil") yeni bir renk rastgele eklenmedi, mevcut sistemle AYNI stilde (soft-bg + ink metni, hem açık hem koyu tema) tek bir yeni `info` tonu (--color-info, muted teal) eklendi, sadece Swing'e atandı.

## Faz 321 — R:R kalibrasyonu: gerçek MAE/MFE verisiyle yön-bazlı target_atr_mult/stop_atr_mult (2026-08-20)

Kullanıcının duraklattığı "Otomatik R/R kalibrasyonu" işi tamamlandı. `analytics/mae_mfe.py::compute_optimal_barrier()` gerçek orta-vadeli (4h/1d, `timeframe` sınıflandırması) kapanmış işlem MAE/MFE'siyle (1098 örneklem, %99.5 kapsam) çalıştırıldı. Güçlü bir yön asimetrisi bulundu:
- **LONG:** empirik en-iyi stop %3.30, hedef %9.09 (oran ~2.75), EV **+%5.85** — hedefler şimdiye kadar çok erken kesiliyormuş.
- **SHORT:** empirik en-iyi ayarda bile hedef ~%0, EV **-%2.46** (negatif) — bu vadede SHORT'un R:R ayarıyla düzelebilecek bir kenarı yok.

Kullanıcı kararıyla (2x AskUserQuestion): tek global `stop_atr_mult`/`target_atr_mult` yerine yön-bazlı 4 ayar (`stop_atr_mult_long`/`target_atr_mult_long`/`stop_atr_mult_short`/`target_atr_mult_short`). LONG'da Faz 261'deki AYNI yöntem (stop sabit, hedef empirik oranla ölçeklenir): 2.5 × 2.7548 ≈ **6.89**. SHORT bilinçli olarak ESKİ değerinde (1.4) bırakıldı — negatif EV'den türeyen bir oranı doğrudan uygulamak anlamsız bir sonuç üretirdi, SHORT'un kendisi ayrı bir inceleme konusu (todo'ya eklendi).

`engines/cognitive_pipeline.py::RiskTargetStage._load_multipliers()` artık `direction` parametresi alıyor (opsiyonel — bilinmiyorsa stop_mult ikisi için aynı olduğundan sorun çıkmıyor). 4 gerçek çağıran güncellendi: `services/macro_shadow_tracker.py::_atr_based_distance_pct` (artık direction parametresi alıyor), `services/benched_agent_shadow_tracker.py` (dissent'lerin ortak yönü çıkarılıyor — "not final" tek bir zıt yön bırakıyor), `services/pairs_trader.py::_open_leg` (zaten bilinen direction'ı geçiriyor), `services/tp_sl_confluence_gatherer.py` (yön-agnostik ölçüm — artık LONG/SHORT mesafeleri BAĞIMSIZ hesaplanıyor). `llm_tools.py`'nin LLM denetim aracı 4 yeni anahtarı raporluyor.

## Faz 320 — Dashboard'a "Güncel kasa" kartı (2026-08-20)

Kullanıcı bulgusu: "Settings'te kasa 500k dolar fakat 2m dolardan fazla harcama yapılmış görünüyor ilginç bir tutarsızlık... Kasada toplam ne kadar para olduğunu görebileceğim hiçbir yer yok." Araştırıldı, GERÇEK sayılarla doğrulandı: `starting_capital`=$500.000, `deployed_notional` (tüm-zamanlar toplam işlem hacmi, 1392 kapanmış işlem üzerinden)=$2.751.607 — bu bir tutarsızlık/bug DEĞİL, aynı sermayenin tekrar tekrar kullanılmasının doğal sonucu, ama "kullanılan" etiketi kafa karıştırıyordu. Gerçek güncel kasa = starting_capital + total_pnl = **$573.106,74** (500k + $73.106,74 gerçekleşmiş kâr) — bunu gösteren HİÇBİR kart yoktu, gerçek bir eksiklik.

`api/rest/positions.py::performance_summary`'nin zaten döndürdüğü `starting_capital`/`all_time.total_pnl` üzerinden (yeni API çağrısı gerekmedi) Dashboard'a en öne yeni bir "Güncel kasa" `StatCard`'ı eklendi. Ayrıca "Strateji getirisi" kartındaki kafa karıştırıcı "kullanılan: $X" alt-yazısı "tüm-zamanlar hacmi: $X" olarak netleştirildi. Açık pozisyonların gerçekleşmemiş kâr/zararı bu kartta YOK (kasıtlı — kapanmış işlemlerle güncellenen gerçek/elde sermaye, floating bir sayı değil).

Aynı düzenlemede: `TRADE_TYPE_LABELS`'ta `scalp`/`hedge` etiketleri commit edilmemiş, önceki bir oturumdan kalma bir düzenlemeyle silinmiş halde bulundu — backend (`api/rest/positions.py::_classify_trade_type`) hâlâ bu iki türü üretiyor, silinmesi devam etseydi dashboard'da bu türdeki işlemler ham `scalp`/`hedge` anahtar adıyla (büyük harf/Türkçe çevirisiz) görünecekti. Geri eklendi.

## Faz 319 — AgentMemory: JSON dosyasından Postgres/TimescaleDB'ye taşındı (2026-08-20)

Kullanıcı isteği: duraklatılmış "AgentMemory JSON -> Postgres" işini bitirip kapatalım. `services/agent_memory.py` tek dosyalı, fcntl kilitli bir JSON'du (54.402 gerçek kayıt, 10 domain) — `decisions`/`weight_approvals` ile AYNI TimescaleDB hypertable deseni (`faz161`) uygulandı: yeni `agent_performance_records` tablosu (`faz319` migration, hem quantdb hem quantdb_test'e uygulandı), `id+timestamp` bileşik birincil anahtar, `(namespace, agent_domain, timestamp)` indeksi.

**`namespace` sütunu — kritik test-izolasyon detayı.** 38 test çağrı noktası `AgentMemory(storage_path=str(tmp_path/...))` ile GERÇEK izolasyon alıyordu (her test kendi boş JSON dizinini kullanır). Bunu Postgres'te birebir korumak için `storage_path` artık doğrudan `namespace` sütununa yazılıyor/filtreleniyor — hiçbir test çağrı noktası değişmedi. Gerçek/canlı kayıtlar `namespace=''` kullanıyor. `AgentMemory` sınıfının public API'si (`record`/`domains`/`get_filtered_records`/`get_summary`/`get_contextual_confidence`) BİREBİR korundu — 8 gerçek caller'ın (`source_reliability_agent.py`, `collective_intelligence_gatherer.py`, `confidence_calibration.py`, `direction_prediction_v2_gatherer.py`, `learning_loop.py`, `position_closer.py`, `expert_council.py`) hiçbiri değişmedi.

**Regresyonda yakalanan gerçek bulgular:**
1. `services/confidence_calibration.py`'de 2 fonksiyon `memory._records` özel alanına doğrudan erişiyordu (public API'yi atlayarak) — `get_filtered_records()`e geçirildi.
2. 4 test dosyası da aynı özel alana erişiyordu — public API'ye geçirildi (`total_record_count()` yeni, minimal bir yardımcı metod olarak eklendi, ham/filtresiz toplam sayı gerektiren testler için).
3. **Gerçek kirlilik bulgusu:** `tests/test_position_close_feeds_agent_learning.py`'deki 2 test bare `AgentMemory()` (varsayılan paylaşımlı test namespace'i) kullanıyordu — JSON'da bu, sıralı test çalıştırmasında "insertion order = benim son kaydım" tesadüfiyle çalışıyordu, ama Postgres implementasyonu (mevcut, değişmemiş `_effective_decision_timestamp` sıralamasıyla, Faz 268-sonrası doğru davranış) başka bir testin AYNI paylaşımlı namespace'e yazdığı, farklı zaman damgalı bir kaydı `[-1]` olarak döndürünce gerçek bir cross-test kirlilik AÇIĞA ÇIKTI (`assert 'test_regime_dedup_bearish_...' == 'bullish_high'`). `tmp_path` ile izole edilerek düzeltildi — production mantığı hiç değişmedi, sadece test izolasyon açığı kapatıldı.

**Veri taşıma:** `scripts/migrate_agent_memory_to_postgres.py` (tek seferlik, idempotent — `ON CONFLICT (id,timestamp) DO NOTHING`) çalıştırıldı: **54.402 gerçek kayıt** (technical 9267, macro 8700, sentiment 5805, onchain 5385, pattern 6602, quant 5352, order_flow 6008, time 3517, epistemology 3516, relative_strength 250) `namespace=''` ile taşındı, doğrulandı (`AgentMemory().get_summary(domain)` gerçek sayılarla eşleşiyor — ör. macro %74.3 isabetli/4811 kayıt, technical %57.8/7280). Eski `agent_memory_history/agent_memory.json` DOSYASI SİLİNMEDİ (arşiv olarak duruyor, hiçbir kod artık okumuyor).

## Faz 318 — pump_fade'in yön körlüğü: council kârlılık farkı + BTC rejimi kesişim gate'i (2026-08-20)

Kullanıcı canlı bulgusu: "Piyasa yukarı yönlü çok ciddi sinyaller veriyorken pump_fade hâlâ SHORT açmaya devam ediyor, elindeki pozisyonlardan bile anlaması lazım kumar oynadığını." Doğrulandı — canlı sorgu: AI council'in açık LONG'larının **%83'ü kârda** (ort. +%3.33), SHORT'larının **%0'ı kârda** (ort. -%9.72); pump_fade'in son ~48 saatte açtığı 79 SHORT'un **%85'i zararda** (ort. -%3.22, en kötüsü PUMPUSDT -%20.3). Kök neden: `services/pump_fade_strategy.py` bilinçli olarak council/regime zincirinden tamamen izole (Faz 268-sonrası tasarım) — piyasanın genel yönüyle ilgili SIFIR kanıt kullanmıyordu.

Kullanıcı onaylı tasarım (AskUserQuestion): **iki bağımsız sinyalin kesişimi**, SADECE margin küçültme (asla tam kapatma). `_compute_regime_size_multiplier` (density multiplier ile AYNI "sadece küçült" ilkesi, Faz 295):
1. Council'in KENDİ açık pozisyonlarının (experiment_bucket IS NULL) GERÇEK şu anki kârlılık farkı — LONG win-rate >= 0.5 VE (LONG win-rate - SHORT win-rate) >= 0.30. Ham pozisyon SAYISI kasıtlı olarak kullanılmadı: geriye dönük kontrolde 109 kapanmış pump_fade işleminin TAMAMI zaten council'in sayıca LONG ağırlıklı olduğu dönemlerde açılmış (sıfır varyans, ayırt edici değil) — kârlılık farkı gerçekten zamanla değişen bir sinyal.
2. BTC'nin gerçek 200-EMA rejimi (`market_data/features/signal_engine.py::compute_quant_signals`) `bull_trend` ise.

İkisi de doğrulanmazsa çarpan 1.0 (fail-closed, mevcut davranış değişmez). İkisi de doğrulanırsa margin sabit tabana (**0.15**) küçültülür, `density_size_multiplier` ile çarpımsal birleşir. Min örneklem: her yön için >= 5 sembol (az örneklemden karar üretilmez). `run_cycle()` sonucuna `regime_size_multiplier` eklendi, kararın `agent_opinions.data`sına da yazılıyor (izlenebilirlik).

**Test tasarımı notu:** `quantdb_test` canlı doğrulandı — 323 açık 'ai' LONG, 2 açık 'ai' SHORT birikmiş (başka test dosyalarının temizlemediği, `project_shared_test_state_bloat` ile aynı sınıf kirlilik). Gerçek DB ile yazılan bir test bu ambient veriyle karışıp flaky olurdu — bunun yerine `_FakeSession`/`_FakeProvider` ile SQL sorgusunu ve fiyat çekimini tamamen taklit eden, DB'ye hiç dokunmayan testler yazıldı.

## Faz 316 — Çok-zamanlı dilim (HTF) confluence + benched ajan itirazı gölge pozisyon + küçük temizlikler (2026-08-20)

Execution Layer'ın hemen ardından, kullanıcının "Technical Agent iki gün önceye kadar %95 isabetliydi, dünden beri tersi çıkıyor" bulgusundan başlayan bir tur:

**1) Kök neden (gerçek ayar, kod bug'ı değil): `candle_timeframe`/`candle_lookback` 6 gündür `1d`/`5000`'de kalmıştı** (14 Ağustos'ta "admin" tarafından değiştirilmiş, kullanıcı "test için değiştirmiştim, bilerek bırakmadım" dedi) — kısa-vadeli sinyal katmanı 5000 GÜNLÜK bar (~13.7 yıl) üzerinden hesaplanıyordu, VWAP sapması gerçek dışı değerler (ör. OPUSDT için -%89.76) üretiyordu. Varsayılana (`15m`/`100`) döndürüldü, `trade_horizon` da (`long`→`medium`) düzeltildi.

**2) Çok-zamanlı dilim (HTF) confluence — gerçek ölçüm + kullanıcı onaylı iki yönlü wiring.** Kullanıcı bulgusu doğru bir mimari boşluğa işaret ediyordu: kısa-vadeli/orta-vadeli katmanlar birbirinden habersiz, tek bir ajan asla iki zaman dilimini birlikte okumuyordu. Gerçek geçmiş 4h Binance verisiyle (feature_ic.py metodolojisi, lookahead'siz, iki bağımsız çalıştırma) ölçüldü: technical_agent'ın kısa-vadeli yönü 4h EMA12/26 trendiyle AYNI yöndeyken kazanma oranı **%41.6** (n=911), TERS yöndeyken **%74.7** (n=438) — sezgisel "confluence" beklentisinin tam tersi. Kullanıcı kararıyla (AskUserQuestion) **iki yönde de** wiring: `market_data/features/signal_engine.py::compute_higher_timeframe_trend` (zaten çekilen risk-timeframe barlarını yeniden kullanıyor, ekstra ağ isteği yok) → `TechnicalContext.higher_timeframe_trend` → `agents/technical_agent.py`'de SADECE confidence çarpanı (`htf_agreement_confidence_multiplier=0.75`, `htf_disagreement_confidence_multiplier=1.15`, 0.85 tavanı korunuyor) — direction ASLA değişmiyor. `meta_optimizer/agent_tuner.py::FIELD_BOUNDS`'a yeni katsayılar için sınır eklendi (gerçek regresyon, testte yakalandı).

**3) Benched ajan itirazı — gölge pozisyon testi (kullanıcı: "günlerdir listede bekliyor").** `services/macro_shadow_tracker.py`'nin izolasyon deseni tekrarlandı: yeni `services/benched_agent_shadow_tracker.py`, bir domain benched olup (`agents/source_reliability_agent.py`) final karardan FARKLI yön önerdiğinde `source="benched_<domain>"` ile sanal pozisyon açıyor — `contracts/shadow_position.py`/`ShadowPositionRepository` zaten source-parametrikti, şema değişikliği gerekmedi. `close_due_benched_shadow_positions_task` (celery beat, macro ile aynı cadence) + `GET /shadow/comparison?source=...` (artık genel) + `GET /shadow/sources` (hangi domain'ler itiraz etmiş, keşif).

**4) Küçük temizlikler:** Transactions.tsx'te kapalı işlem kartında "Kaldıraç" alanı koşullu render ediliyordu (leverage yoksa DOM'dan tamamen çıkıp sonraki hücreleri sola kaydırıyordu) — `OpenPositionRow`'daki "hep render + spot fallback" desenine getirildi. `contracts/experiment_registry.py` (Faz 233'te tablosu kaldırılmıştı, kod tamamen ölüydü — `engines/cognitive_pipeline.py`'de kullanılmayan bir import dışında hiçbir gerçek çağıran yoktu) tamamen silindi.

**5) NUPL/SOPR/Realized Price eklendi (kota tekrar açılınca canlı doğrulandı, 2026-08-20).** `market_data/onchain/onchain_provider.py`'ye MVRV ile AYNI ücretsiz kaynak/önbellek deseniyle üç yeni fetch fonksiyonu (`fetch_nupl`/`fetch_sopr`/`fetch_realized_price`) — üçü de canlı test edildi (sırasıyla 0.2452 / 1.0012 / 52255.99$). `mvrv_ratio`/`mayer_multiple` ile AYNI kasıtlı kapsam: henüz hiçbir ajana/pump_fade'e bağlanmadı, SADECE gözlem — kalibrasyon için gerçek veri birikmesi gerekiyor. Bu değişiklik henüz commit edilmedi.

**Açık kalan takip maddesi:** commit onayı bekleniyor (Execution Layer/Faz 316 gibi, henüz istenmedi).

## Faz 315 — Execution Layer, Faz 1: gerçek Binance Futures Testnet emir gönderimi (2026-08-20)

Kullanıcı: "Execution Layer'den devam edelim." Sistem baştan sona saf simülasyondu (`simulator/fill_engine.py` uydurma dolum fiyatı, `position_closer.py` periyodik fiyat-yoklamasıyla "kapandı" kararı) — BOME (-$17.5K)/MUBARAK (-$16.9K) kayıplarının kök nedeni tam olarak buydu: kontrol döngüsü fiyatın stop seviyesini AŞTIĞINI bir SONRAKİ yoklamada fark ediyordu. Plan Mode ile mimari onayı alındı (`~/.claude/plans/velvety-whistling-parasol.md`), 3 kritik karar kullanıcıdan: **sembol bazında** opt-in (`execution_mode_symbols`), **STOP_MARKET/TAKE_PROFIT_MARKET** (limit değil), ve kullanıcının ısrarla eklediği kritik gereksinim — **"Hayır, breakeven/trailing testnet'te de en baştan olmalı"** (agent'ın Faz-1-erteleme önerisini reddetti).

**Yeni**: `contracts/exchange.py::OrderExecutionPort` (+OrderSide/OrderType/OrderStatus/PlaceOrderRequest, BİLEREK senkron); `exchange_gateway/binance/futures_execution_adapter.py` (HMAC-SHA256 imzalı, testnet.binancefuture.com sabit, mainnet'e Faz 1'de kod içinde bile erişilemez); `exchange_gateway/binance/rate_limit.py` (mevcut Redis throttle adapter.py'den çıkarıldı, futures adaptörüyle paylaşılıyor); `services/execution_service.py::ExecutionService` (tek orkestrasyon noktası — açılış: MARKET giriş + STOP_MARKET/TAKE_PROFIT_MARKET koruma; ratchet: iptal+yeniden-koy, başarısızlıkta önce eski fiyatı yeniden koymayı dener, o da başarısızsa ACİL MARKET kapatış + `EventLogRepository`'ye KRİTİK olay — "bir leveraged pozisyonun sınırsız süre korumasız kalmasına asla izin verilmez"); `services/execution_reconciliation.py` + `reconcile_execution_state_task` (5dk'da bir, DB/borsa mismatch'ini SADECE işaretler/loglar, otomatik düzeltmez).

**Değişen**: `services/decision_recorder.py` (execution_mode=="testnet" ise gerçek dolum fiyatı/miktarı kullanır, emir teyit edilemezse fail-closed no_trade); `services/position_closer.py` (testnet pozisyonlarında kendi iç fiyat-karşılaştırmasını — BOME/MUBARAK'ı üreten TAM O mekanizmayı — atlayıp borsanın gerçek durumunu sorar); `decisions` tablosuna 6 yeni nullable sütun (migration `faz315`, hem `quantdb` hem `quantdb_test`'e uygulandı); Transactions.tsx'e "testnet" rozeti.

**Mimari not**: `execution_mode` (simulated/testnet, YENİ) ile `trading_mode` (test/live, Faz 188'den beri var) KASITLI OLARAK ayrı, örtüşmeyen kavramlar — biri emir gönderimini, diğeri sadece risk-teşhis sıkılığını kontrol ediyor.

**Test**: `test_futures_execution_adapter.py` (httpx.MockTransport, imzalama+istek inşası+hata kodları), `test_execution_service.py` (sahte adapter, happy-path+fail-closed+emergency-close), `test_execution_reconciliation.py`, `test_decision_recorder_execution_mode.py`, `test_position_closer_execution.py` — hepsi gerçek ağ/anahtar gerektirmiyor. Varsayılan `execution_mode="simulated"` davranışının HİÇ değişmediği ayrıca doğrulandı.

**Mid-implementation'da yakalanan bug (commit'ten ÖNCE düzeltildi)**: `get_order_status`/`cancel_order` başta `client_order_id` alıyordu ama koruma (stop/TP) emirlerinin client_order_id'si DB'de HİÇ saklanmıyor — sadece borsanın atadığı numerik `exchange_stop_order_id`/`exchange_tp_order_id` var. Port/adaptör/servis `order_id` (numerik) kullanacak şekilde düzeltildi.

**Kullanıcının henüz testnet API anahtarı yok** — "Şimdilik sadece mimariyi/planı konuşalım, anahtar sonra" dedi. Anahtarsız durumda `ExecutionService.is_configured()` False döner, sistem tamamen `execution_mode="simulated"` (bugünkü davranış) gibi çalışmaya devam eder — bu Faz'ın tamamı anahtar OLMADAN kodlanıp mock'lu testlerle doğrulandı.

**Açık kalan takip maddesi:** commit + servis restart (kullanıcı onayı bekleniyor); gerçek testnet anahtarları gelince tek sembolde uçtan uca canlı doğrulama (listenin en sonuna bilerek bırakıldı).

## Faz 279-289 — Backtest kaldırıldı, veri hijyeni kök nedene inildi, pump_fade/ağırlık/LLM-denetim düzeltmeleri, Grup B'nin son 4 modülü, 4 yeni TA göstergesi (2026-08-19)

Önceki turun "açık kalan takip maddesi" olan yatay-piyasa riski hâlâ kasıtlı olarak ertelenmiş durumda (bkz. aşağıdaki dış-rapor değerlendirmesi) — bunun yerine kullanıcının gerçek, o gün yaşanan bulgularıyla başlayan, günü kaplayan bir tur:

**1) Backtest alt sistemi tamamen kaldırıldı (Faz 284, c158bfd).** Kullanıcı: "Bu backtestten daha önce elde ettiğim verileri ajanlar kullanabiliyor mu?" Grep tabanlı bağımlılık izlemesiyle doğrulandı: `backtest_agent_memory_history/` (Faz 268i'den beri canlıdan İZOLE) hiçbir production kodu (WeightOptimizer, SourceReliabilityAgent, `meta_optimizer/agent_tuner.py`) tarafından okunmuyordu — karar mekanizmasına sıfır katkısı olan, sadece celery kaynağı tüketen ölü bir alt sistemdi. `backtest/{backtest_orchestrator,cognitive_backtest_runner,real_historical_backtest,vectorized_engine,walk_forward,cross_validation,portfolio_sim,stress_scenarios}.py` + `api/rest/backtest.py` + BacktestRuns.tsx + `backtest_runs` tablosu silindi. Korunanlar: `red_team.py` (kill switch stres testi) ve `embargo_walk_forward.py` (haftalık ajan ayarlama) — `red_team.py`'nin gerçekten ihtiyaç duyduğu 2 fonksiyon doğrudan içine taşındı.

**2) Kirli geçmiş veri — scalp/hedge/pump_fade açık pozisyonları `excluded_from_stats`'a taşındı (Faz 279-281, 283).** Kullanıcı: "Geçmişteki kirli işlemlerden hala açık olanlar var... bunları hiç açılmamış gibi sistemden çıkaramaz mıyız?" 4 migration (silme değil, Class 2 ilkesi — işaretleme) + kritik bir propagation-gap düzeltmesi: `excluded_from_stats` önceden SADECE dashboard/stats sorgularında okunuyordu, `_record_agent_learning()` (ajan öğrenme pipeline'ı) ve `_breakdown_by_trade_type()` (dashboard kırılım tablosu) bu bayrağı hiç görmüyordu — ikisi de artık filtreliyor.

**3) Hedge (pairs trading) tamamen durduruldu.** Kullanıcı önce "az işlem açıyor, işe yaramaz" dedi sonra "tamamen kaldıralım bir daha hedge işlemi almasın" diye netleştirdi. `pairs_trading_enabled=false` AppSetting + `pairs_trader.py`'de erken çıkış + Settings.tsx'teki kart tamamen kaldırıldı (`AppSettingsRepository.DEFAULTS`'te varsayılan artık false).

**4) pump_fade_v1 breakeven/trailing — mutlak yüzdeye geçirildi (b82e532).** Kullanıcı gerçek zamanlı bulgu: "Bugün açılan pump pozisyonlarında çoğu işleme karlı başladı sistem yön değişimini algılayıp doğru zamanda çıkış yapamıyor." Kök neden: pump_fade sabit, geniş bir stop (`%30`) kullanıyor ama breakeven/trailing tetikleyicileri bu geniş stop mesafesinin R-katı olarak hesaplanıyordu — pump_fade'in gerçek MFE'leri (%0.4-5) bu eşiği hiçbir zaman geçemiyordu. `_apply_breakeven_stop()` artık `experiment_bucket=="pump_fade_v1"` için `entry_price`'a göre mutlak yüzde eşikleri (`pump_fade_breakeven_trigger_pct=0.01`, `pump_fade_trailing_stop_distance_pct=0.007`) kullanıyor; AI council pozisyonları etkilenmedi. Canlı doğrulama: HEMIUSDT/SHORT pozisyon kâr ile stop oldu (kullanıcı: "yeni düzenlememiz işe yarıyor gibi görünüyor").

**5) Ağırlık önerisi çalkantısı — 6 saatlik soğuma + tek-domain medyan kopyalama hatası (eb0e86e).** Kullanıcı gerçek ekran görüntüleriyle: "5 farklı rejim önerisi birbirinden çok farklı... her işlem kapandığında değişiklik yapıyor... matematiğinde %100 problem var." İki ayrı kök neden: (a) `close_due_positions()` her pozisyon kapanışında `propose_weights()`'ı tetikliyordu, `has_pending()` sadece O ANKİ bekleyen onayı kontrol ediyordu — reddedilir edilmez bir sonraki kapanış hemen yeni öneri üretebiliyordu; artık rejim başına, durumdan bağımsız 6 saatlik soğuma var (`weight_proposal_cooldown_hours`). (b) `domains_needing_fallback` medyan hesabı, tek bir veri-güdümlü domain varken o domain'in kendi skorunu diğer TÜM domain'lere kopyalıyordu (gerçek örnek: `technical=1.77`, tek gerçek veri, `macro/onchain/pattern/quant/...` hepsi 1.770 olmuş) — artık medyan sadece ≥2 domain varken kullanılıyor, tek domain varsa nötr 1.0.

**6) LLM denetim döngüsü — erken boş cevapla bitiyordu (eb0e86e).** Kullanıcı 3 ayrı gerçek çalıştırmada (8/9/12 gerçek araç çağrısı, hepsi `max_iterations=15`'ten çok önce) "Araç çağrı döngüsü sınırına ulaşıldı" hatası bildirdi. `llm_audit_runs`'daki gerçek kayıtlarla kök neden bulundu: model max_iterations'a ulaşmadan kendiliğinden araç çağırmayı bırakıp BOŞ içerik döndürüyordu (üst üste binen `search_code` sorgularıyla takılıp pes ediyordu). Artık bu durumda modele `tool_choice="none"` ile bir kez daha, iterasyon bütçesini tüketmeden şans veriliyor (`_force_final_answer`).

**7) Grup B'nin son 4 modülü canlıya bağlandı (Faz 285-288, d256944).** Meta-Learning Effectiveness, Market World Model, Direction Prediction v2, Opportunity Quality — Cognitive Core 2.0-11.0'da zaten yazılmış ama hiç wire edilmemiş analytics fonksiyonlarını gerçek DB verisiyle besliyor. `mae_mfe_confidence` ile AYNI desen (gatherer + contract + repository + haftalık celery task + API router + dashboard sayfası). Dördü de Grup B: council'i hiç etkilemeyen salt ölçüm/rapor katmanı — kullanıcı normalde tek-tek/gözlem-pencereli aktivasyon istiyor ama bu dördünün karar hattına hiç dokunmadığını görünce "bu sefer 4'ünü birden bağla, istisna yap" dedi.

**8) Pivot Points/Keltner/Donchian/Parabolic SAR eklendi (Faz 289, 46f8f95).** Kullanıcı, destek/direnç araştırması sırasında `signal_engine.py`'nin kendi Faz 237 yorumunun "gelecek aday" olarak not ettiği üç yöntemi (Parabolic SAR/Keltner/Donchian) + Pivot Points'i (Classic/Camarilla/Woodie) istedi. Standart, deterministik formüllerle eklendi — saf hesaplama katmanı, henüz hiçbir ajanın oyuna ya da `RiskTargetStage`'in stop/target hesabına bağlanmadı.

**Üçüncü taraf AI rapor doğrulama disiplini (devam ediyor):** Kullanıcının paylaştığı bir dış "mimari inceleme" raporu ("Adaptive Barrier canlı hatta wire edilmemiş", "gerçek EV kapısı yok", "range/chop filtresi yok" iddialarıyla) kod tabanına karşı doğrulandı — üçü de YANLIŞ çıktı: `adaptive_barrier_enabled=true` ve `RiskTargetStage._try_adaptive_barrier()` zaten canlı; `services/kelly_sizing.py::kelly_size_multiplier` confidence-kovası bazında gerçek win_rate/avg_win/avg_loss'tan EV negatifse boyutu sıfırlıyor (fiilen bir EV kapısı, sadece etiketlenmemiş); `MetaStage`'de `adx<20 AND long_term_trend_regime=="transition" → WAIT` zaten var. Raporun haklı çıkan/kalan gerçek boşlukları: bu üç mekanizmanın hiçbiri rejim+ajan-konsensüsü+ikinci-sinyal (Hurst/bandwidth) ile koşullu değil — bu, bir sonraki turun doğal önceliği.

**Açık kalan takip maddeleri:** yatay piyasa riski hâlâ kasıtlı olarak ertelenmiş; ajan/feature ablation (nedensel katkı ölçümü) canlı döngüde yok — sadece davranışsal auto-bench var; PUMP-FADE stop-loss'unun gerçek tarihsel ters-dönüş olasılığından istatistiksel türetilmesi henüz başlamadı; QUANT ajanının performans gerilemesinin kök nedeni (Hurst/z-score/otokorelasyon rejim mantığı) henüz araştırılmadı — sadece "benched, %20 son-20-isabet" yüzeysel bulgusu var.

## Faz 268-sonrası (devam) — Explain butonu, Concept Drift canlı-mod kısıtı, karar kalitesi kapıları, LLM denetçi (2026-08-14)

Kullanıcının Transaction/Dashboard sayfalarındaki gerçek "Açıkla" raporlarını okuyup somut sorunlar bulmasıyla başlayan, günü kaplayan bir tur:

**1) `GET /positions/{id}/explain` + Transactions "Açıkla" modalı (c81cd3f, 069ad37, add0dc4):**
Hangi ajandan ne karar geldiğini gösteren, `agent_contributions`'ı ayrıştıran endpoint + hem açık hem kapalı pozisyonlarda modal. Kullanıcı bulgusu: `.glass-panel`'in kasıtlı %8-32 opaklığı (site geneli "cam" tasarımı) modal içinde arkadaki sayfa içeriğinin metinle çakışmasına yol açıyordu — `Card`'a `opaque` prop'u (`.modal-panel`, %96 opak) eklendi, hem Explain hem Tokens kaldıraç modalında kullanıldı (tasarım tutarlılığı).

**2) Concept Drift — dashboard göstergesi + sadece canlı modda pozisyon engelleme (069ad37, de23631):**
`get_concept_drift_diagnostics()` dashboard'a taşındı. Kullanıcı bulgusu: test modunda gerçek sermaye riski yokken bu koruma veri toplamayı gereksiz yere durduruyordu — artık sadece `trading_mode="live"` iken `RiskReason` üretiyor (`enforced` alanıyla ayırt ediliyor). Ayrı bulgu: panelde üç farklı "kazanma oranı" (tüm-zamanlar %59, concept-drift baseline %52, recent %0) çelişki sanılıyordu — banner metni artık pencereleri açıkça etiketliyor.

**3) Backtest task'ları deploy restart'larında sessizce kayboluyordu (42a6020):**
Kullanıcı bulgusu: "sen servisleri kapatıp açtıkça backtestler kapanıyor." Celery varsayılanı `task_acks_late=False` — worker öldürülünce mesaj bitmeden kuyruktan siliniyordu. Sadece 3 backtest task'ına (`run_backtest_task`, `run_real_backtest_task`, `run_portfolio_backtest_task` — idempotent, tek etkileri kendi `backtest_runs` satırı) `acks_late+reject_on_worker_lost` eklendi; gerçek pozisyon açan task'lara BİLEREK eklenmedi (yeniden çalıştırma aynı sinyali ikinci kez pozisyona çevirebilir).

**4) Karar kalitesi — güçlü tek-ses itirazı freni + Faz 207 test-modu tabanının kaldırılması (f61f2e6):**
İki gerçek "Açıkla" raporu (ADAUSDT %19.1 güven, technical ajanı %87 güvenle VE kalibrasyon x1.09 ile TERS yöne işaret ederken yine de LONG açılmış; başka bir örnekte 10 ajandan 7'si "benched"ken kalan 2 zayıf ses %16.9 güvenle pozisyon açmış) somut mimari eksikleri ortaya çıkardı:
- `MetaStage` artık `opinions`'a bakıyor: benched olmayan herhangi bir ajan nihai yönün TERSİNE %75+ güvenle işaret ediyorsa WAIT.
- Faz 207'nin test-modu `reduce_threshold=0.05` tabanı KALDIRILDI (kullanıcı: "confidence değerinin önemi yok, 20 ile de 80 ile de pozisyona giriyorsa bu veri bir anlam ifade etmiyor"). Her iki gerçek "kumar" örneği de SADECE bu düzeltmeyle zaten WAIT'e düşüyor.
- Denenip TERK EDİLEN üçüncü fikir: sabit "en az N aktif ajan" eşiği. Gerçek 23.221 kararlık geçmiş veriyle ölçüldü — katılımcı sayısı ile confidence ZIT yönde ilişkili (tek çelişkisiz ses confidence'ı yapay yükseltebiliyor); sabit eşik geçmişin ~%64'ünü ayrım gözetmeksizin bloke ederdi. Kullanıcının "iki uç noktada gidip geleceğiz" endişesi veriyle doğrulandı, eklenmedi.
- Watchlist 20→37 sembole çıkarıldı (17 yeni likit Binance Futures paritesi, TRADING durumu API ile doğrulandı) — kullanıcı tercihi: "işlem sayısını artıracaksak coinleri artıralım," veri hacmi artık sembol çeşitliliğiyle karşılanıyor, tek sembolde karar kalitesinden ödün verilmiyor.

**5) Faz 271 — LLM periyodik sistem denetimi (74a7353):**
Kullanıcı: "LLM var yazışabiliyoruz sadece mimariye entegre edilmemiş... karar mekanizmasına dahil etmemiz lazım." Ama net tercih: karar LLM'e bırakılmayacak, mekanik sistem daha güvenilir — LLM DENETLEYİCİ. `services/llm_system_audit.py::run_system_audit()`, her 6 saatte bir (`llm_system_audit_task`, celery beat) `NvidiaDecisionCritic.ask_with_tools()`'u (zaten var olan 6 araçla) kendiliğinden tetikliyor, somut sorun bulursa ZATEN VAR OLAN `code_change_proposals` kuyruğuna (Faz 270, insan onaylı) öneri düşürüyor. Yeni `llm_audit_runs` tablosu + dashboard'da "LLM Denetim Geçmişi" bölümü — "hiçbir şey bulamadım" dahil her çalışma görünür (aksi halde çalıştığına dair hiçbir iz olmazdı).

**Açık kalan iki takip maddesi:** R/R canlı doğrulama (zamana ihtiyaç var); yatay piyasada pozisyon açma riskinin azaltılması (kullanıcı isteğiyle en sona ertelendi).

## Faz 268q-268y — Kill switch/RiskGate kök-neden turu, R/R yeniden kalibrasyonu, LLM Decision Critic (2026-08-13)

Cognitive Core 2.0-11.0 senteziyle biten önceki tur sonrası, kullanıcının
paylaştığı dış bir "inceleme" ("sürekli SL yiyoruz") gerçek kod/veriyle
doğrulanarak başlayan, günü kaplayan bir kök-neden ve düzeltme zinciri:

**1) Kill switch — eski ağırlık kuyruğu sayacı kırmızıda tutuyordu (268q):**
Gerçek olay: `technical_agent` ağırlığı 8 gün (1.42, aşırı ağırlıklı) sabit
kaldıktan sonra düşürüldü, ama o eski rejimle açılmış 700+ pozisyonluk
kuyruk günlerce kapanmaya devam etti. Ardışık-kayıp sayacı AÇILMA değil
KAPANMA sırasına bakıyor — her manuel "Başlat" birkaç dakika içinde geri
alınıyordu. `kill_switch_legacy_cutoff_at` ayarı: bu tarihten önce açılmış
pozisyonlar SADECE kill switch sayacından çıkarılıyor (dashboard
istatistikleri etkilenmiyor, Class 2 ilkesi — hiçbir satır silinmiyor).
Doğrulama: yeni-ağırlık kohortu (131 kapanan) %86.3 kazanma, eski-ağırlık
kohortu (1300 kapanan) %58.5 — sorun yeni kararlarda değil, eski kuyrukta.

**2) ENB tabanlı portföy sıkılaştırması (268o) + aynı sembol/yön tavanı (268t):**
Effective Number of Bets düşükken TÜM önerilen sembollere confidence
indirimi (Cognitive Core 2.0/M6, ilk gerçek canlı bağlantısı). Ayrı, daha
büyük bulgu: XAUTUSDT'de aynı yönde (SHORT) **54 pozisyon** aynı anda açık
kalabilmişti — `max_concurrent_positions` TOPLAM sayıya bakıyor, ENB/
Cross-Symbol Correlation Filter sadece AYNI cycle'daki eşzamanlı önerilere
bakıyor, hiçbiri SAATLER içinde BİRİKEN aynı-yönlü pozisyonu görmüyordu.
`max_open_positions_per_symbol_direction` (varsayılan 5) eklendi.

**3) RiskGateStage test-modu bypass'ı (268t) — gerçek regresyon:** Faz 262
bu bypass'ı RiskEngine.execute()'dan (ön kapı) kaldırmıştı ama RiskGateStage
(son kapı, final_size/concurrent-position/capital-% kontrolleri) gözden
kaçmış — sistem `trading_mode="test"` iken bu kontroller BAŞTAN BERİ fiilen
devre dışıydı. Kaldırıldı, artık test modunda da tüm kontroller uygulanıyor.

**4) DEFAULT_LOOKBACK 100→230 (268u):** `run_real_backtest`'in walk-forward
penceresi asla büyümüyor — `_long_term_trend_regime` en az 220 bar istiyor,
eski varsayılan bu özelliği HİÇBİR backtest'te hiç çözülemeyecek şekilde
kilitliyordu (1512 işlemlik bir OOS koşusunda regime %100
"insufficient_data" çıktı). Düzeltildi, canlıyı etkilemiyor (canlı zaten
yeterli geçmişe erişiyor, doğrulandı).

**5) Adaptive Barrier Engine OOS doğrulaması (268r) + R/R yeniden
kalibrasyonu (268v):** `analytics/adaptive_barrier_oos_validation.py` —
train/test split + embargo + Deflated Sharpe Ratio ile gerçek doğrulama.
Sonuç: `RiskTargetStage`'in Faz 261'den beri sabit 1:4 oranı (STOP=2.5x,
TARGET=10.0x günlük ATR) — gerçek temiz veride (1312 işlem, DEFAULT_
LOOKBACK düzeltmesinden SONRA) test setindeki 384 işlemin TAMAMI stop_loss
ile kapandı (ortalama MFE %0.38 ≪ ortalama |MAE| %1.28). Ampirik en iyi
oran ~1:0.545 — TARGET_ATR_MULT 10.0'dan **1.4**'e çekildi. DSR henüz
"genuinely_skillful" eşiğini geçmiyor (0.012, 65 örneklem) — yön güçlü,
istatistiksel kanıt tam değil — bu yüzden STOP_ATR_MULT/TARGET_ATR_MULT
artık sınıf sabiti değil, AppSettings'ten okunuyor (redeploy gerekmeden
kalibre edilebilir).

**6) SL sonrası fiyat geri dönüşü ölçümü (268s):** `analytics/sl_recovery_
analysis.py::compute_post_exit_recovery` — SL'den SONRAKİ gerçek fiyat
yoluna bakıp breakeven'a dönüp dönmediğini ölçüyor (compute_mae_mfe/
compute_optimal_barrier'ın HİÇBİRİ kapanıştan sonrasına bakmıyordu). İlk
gerçek sonuç (52 SL işlem, ~36-41dk pencere): 0/52 breakeven'a döndü,
hepsi aleyhte devam etti — "stop'lar erken tetikleniyor" hipotezinin
tersi. Örneklem küçük/kümeli (~2 bağımsız olay), tekrar bakılmalı.

**7) LLM Decision Critic — NVIDIA NIM entegrasyonu (268w-268x):**
`OllamaExplainer` (yerel Ollama, kullanıcı bulgusu: yetersiz) yerini
`NvidiaDecisionCritic`'e bıraktı — build.nvidia.com'un ücretsiz NIM API'si
(OpenAI-uyumlu), adversarial/eleştirmen system prompt'uyla (açıklama değil
İTİRAZ). Gerçek A/B test (aynı gerçek karar payload'ı): `deepseek-ai/
deepseek-v4-flash-0731` (90s) `openai/gpt-oss-20b`'den (5s) belirgin
derecede daha derin eleştiri üretti (Hurst exponent'in rastgele-yürüyüş
bölgesinde olduğunu yakaladı, diğeri kaçırdı); `openai/gpt-oss-120b` bu
yükte tutarlı zaman aşımına uğradı. Varsayılan: deepseek-v4-flash (danışma
amaçlı, canlı işlem kapısı değil — hız yerine kalite). Dashboard'da yeni
"Respond" sekmesi (serbest soru/cevap, `POST /api/v1/llm-critic/
ask`). Kasıtlı olarak sadece danışma — hiçbir karar otomatik reddedilmiyor/
onaylanmıyor; kod-düzenleme/otomatik-deploy YOK (proje kuralı: AI kendine
unilateral canlıya alma yetkisi veremez).

**Açık kalan iki takip maddesi:** confidence=0.663 kümelenmesinin (macro
agent, muhtemelen sembol-bağımsız gerçek makro veriden — teyit edilmedi)
kesin kaynağı; SL-sonrası-geri-dönüş ölçümünün daha büyük/zamana yayılmış
örneklemle tekrarı.

## Faz 268-öncesi — Cognitive Core 2.0-11.0 tamamlandı (25+ yeni analytics modülü)

## Cognitive Core 2.0-11.0 — "Predictive Decision Architecture" yol haritasının ikinci büyük dilimi (2026-08-13)

Faz 268 sonrası (Feature Importance→MAE/MFE koşullu dağılımlar) tamamlandıktan sonra,
kullanıcının onayıyla ("makul bir noktadan başlayalım" / "sen kendi kararınla
somutlaştır") 500-fazlık Predictive Decision Architecture / Cognitive Core yol
haritasının BÜYÜK bir kısmı tek oturumda inşa edildi. Her madde GERÇEK, literatürde
tanımlı bir teknikle somutlaştırıldı — hiçbiri icat edilmiş bir formül değil, hepsi
fail-closed (yetersiz örneklemden sonuç icat edilmez) ve **hiçbiri canlı karar
hattına (services/orchestrator.py, engines/risk_engine.py) WIRE edilmedi** — bu
oturumun tekrarlanan teması "measure first, insan onayı olmadan hiçbir risk/pozisyon
kararını değiştirme."

**Önce ~30 küçük-orta risk/analitik modülü** (Faz 268b-273): MAE/MFE+Barrier tam
katmanı (koşullu dağılım→competing-risk→Optimal Barrier Surface→confidence
ayrıştırma→selection-bias), Seasonality Detection, Correlation Breakdown Detection,
Liquidity-Adjusted VaR, Economic Calendar Integration (FOMC/CPI — GERÇEKTEN canlı
karar hattına wire edildi, epistemology_agent'ı tightening yönünde etkiliyor, data_
quality_score ile AYNI desen), Stablecoin/Pegged-Asset Depeg Risk.

**Sonra Cognitive Core 2.0'ın 10 milestone'ı (M1-M10, Faz 269-768)** eksiksiz
tamamlandı — 18 modül: system_events (olay günlüğü, kill switch tetiklenmesi
GERÇEKTEN kaydediliyor) + Feature Registry (39 feature'ın kataloğu) + Piyasa rejimi
motoru v2 + Price Structure (S/R bölge kümeleme) + Momentum/Mean-Reversion MoE Router
(Hurst-tabanlı) + Microstructure v2 (Kyle's Lambda) + Cross-Asset Lead-Lag + Labeling
(reddedilen fırsatların gerçek bar verisiyle backfill'i) + MAE/MFE Bilimsel Motoru
(bootstrap güven aralıkları) + Adaptive Barrier Engine (lookup) + Direction Prediction
v2 (Brier Score) + Probability Calibration (ECE) + Opportunity Quality/Meta-Labeling
(ajan konsensüsü) + Entry Timing + Expected Utility (CRRA) + Portfolio Intelligence
(Effective Number of Bets) + Backtest Doğrulama (Deflated Sharpe Ratio) + Stress
Testing (Historical Simulation) + Concept Drift (P(Y|X) kayması, feature drift'ten
AYRI) + Meta-Learning Effectiveness (CMA-ES turlarının gerçekten iyileşip
iyileşmediği).

**Sonra Cognitive Core 3.0-11.0'ın somut dilimleri** (kullanıcı onayıyla, her başlık
kendi mühendislik yargımla GERÇEK bir tekniğe indirgendi): Self-Model (birden fazla
bağımsız güvenilirlik sinyalini — ECE/DSR/kill switch/drift — TEK bir öz-değerlendirme
anlık görüntüsünde birleştiren içgözlem), Causal Cognitive Core (Granger Causality —
korelasyonla nedenselliği ayırt eden ilk araç), Market World Model (Moving Block
Bootstrap — mevcut iid bootstrap'in aksine zaman-serisi bağımlılığını koruyor),
Adversarial Intelligence (sistemin GERÇEK geçmişindeki en kötü koşulları bulan
madencilik, sentetik red-team senaryolarından farklı), Scientific Self-Correction
(hipotez retest — bir edge zamanla kayboldu mu, iki-oran z-testiyle dürüstçe tespit),
Collective Research Intelligence (Condorcet Jüri Teoremi — council gerçekten en iyi
tekil ajandan daha isabetli mi), Self-Designing Intelligence Guard (AIProposal —
approve()'un insan kimliği zorunluluğu Python seviyesinde zorlanıyor, "ai"/"system"
gibi kimliklerle kendi kendine onay AÇIKÇA engelleniyor).

**Cognitive Core 12.0 ("General Decision Intelligence vizyonu") kasıtlı olarak bir
koda indirgenmedi** — bu madde somut bir teknik değil, yukarıdaki tüm parçaların
BİR ARAYA GELİŞİNİN kendisi zaten bu vizyonun karşılığı: Feature Registry NE
bildiğimizi, system_events NE OLDUĞUNU, Self-Model NE KADAR GÜVENDİĞİMİZİ,
Causal/Collective/Adversarial/Scientific-Self-Correction modülleri NEDEN
güvendiğimizi sorgulayan bir katman oluşturuyor — "genel karar zekası" tek bir
modül değil, bu senteze verilen isim.

**Sonraki adım:** hiçbiri henüz canlıya wire edilmedi. Bir sonraki oturumun doğal
işi, kullanıcıyla birlikte BU modüllerden hangilerinin (varsa) gerçek OOS
doğrulamadan sonra insan onayıyla canlıya alınacağına karar vermek — AIProposal
guard'ı (Self-Designing Intelligence) tam bunun için hazır.

## Faz 251-268 devamı (2026-08-12 — 2026-08-13)

v1.40.0'dan bu yana eklenenler, hepsi mevcut GERÇEK pipeline'a (backtest
veya canlı) bağlı, ayrı/izole demo kod değil:

- **Feature Importance** (7 oy-veren ajan): `contributions: dict[str, float]`
  + `scale_all()` deseni — technical/order_flow/macro/onchain/sentiment/
  pattern/quant ajanlarının hangi sinyalin skora ne kadar katkı verdiğini
  gösteriyor.
- **Adversarial Red-Team** (`backtest/red_team.py`): whipsaw/flash-crash/
  korele çoklu-varlık çöküşü senaryoları GERÇEK CognitiveEngine/RiskEngine
  üzerinden koşuluyor.
- **Online Feature Selection** (`analytics/feature_ic.py`): özelliklerin
  ham fiyat getirisiyle Information Coefficient'ı, `GET /feature-ic/`.
- **Latency Monitoring**: `decision_pipeline_latency_seconds` histogram —
  ingestion→karar süresi.
- **Model Drift Detection** (`analytics/model_drift.py`): PSI + KS-test,
  baseline vs güncel pencere, `GET /model-drift/`.
- **Data Quality Scoring** (`market_data/features/signal_engine.py`):
  OHLC tutarlılık + "bad print" wick-reversion imzası; epistemology_agent
  düşük skor gördüğünde wait_confidence'ı artırıyor.
- **Backtest'e kill switch/drawdown sizing bağlandı**: `real_historical_
  backtest.py` artık gerçek `consecutive_losses`'ı loop seviyesinde
  simüle ediyor (RiskEngine'in canlı DB yazan tetiğine ASLA dokunmadan),
  `net_pnl_usd` hesaplaması Kelly/drawdown boyut küçültmesini artık
  doğru yansıtıyor (önceki bug: kaldıraçsız `capital_per_trade` kullanıyordu).
- **MAE/MFE ölçüm katmanı** (`analytics/mae_mfe.py`): her trade için
  gerçek bar-path'ten Maximum Adverse/Favorable Excursion. Üzerine
  **koşullu MAE dağılımları** (`compute_conditional_mae_distribution`):
  rejim/volatilite/yön/güven-kovası kombinasyonlarına göre gruplanmış
  empirical MAE quantile'ları (min_group_size=20 fail-closed). Henüz
  gerçek SL hesaplamasına uygulanmıyor — bu adaptive-SL fikrinin
  SADECE ölçüm dilimi.
- **Günlük rapor zero-fill düzeltmesi**: `performance_by_period()`
  artık `generate_series` + `LEFT JOIN` ile veri olmayan günleri de
  0 olarak gösteriyor, tamamen atlamıyor (kullanıcı bulgusu: 12-13
  Ağustos günleri dashboard'dan tamamen kaybolmuştu).
- **Kill switch bildirimi**: dashboard artık `ai_enabled_updated_by`
  ile gerçek kill-switch tetiklenmesini (updated_by='kill_switch')
  manuel Durdur düğmesinden ayırt edip ayrı bir masaüstü bildirimi/alarm
  gösteriyor.
- **Settings'te kill switch eşiği kontrolü**: kullanıcı artık kaç
  ardışık kayıpta AI'nın otomatik durması gerektiğini dashboard'dan
  kendisi ayarlayabiliyor (backend doğrulaması zaten vardı).

**Operasyonel bulgu (önemli):** Data Quality Scoring commit'inden
sonraki birkaç commit (backtest kill-switch wiring, MAE/MFE, koşullu
dağılımlar dahil) canlı uvicorn/celery süreçleri yeniden başlatılmadığı
için bir süre DEPLOY EDİLMEMİŞ durumda çalıştı — kod commit edilmek
production'da çalışmak anlamına gelmiyor. Kullanıcının yapıştırdığı bir
review'u doğrularken (gerçek karar kayıtlarında `data_quality_score`
alanının hiç görünmemesi) fark edildi, servisler yeniden başlatıldı.

**excluded_from_stats ikilemi (bilinen, kasıtlı olarak çözülmemiş):**
Kill switch'in `consecutive_losses` sayacı ile Performance dashboard'un
günlük/özet istatistikleri AYNI `excluded_from_stats` bayrağını okuyor.
Bir kayıp serisini hariç tutup kill switch'i sıfırlamak o serideki
günleri dashboard'dan da gizliyor; geri almak kill switch'i yeniden
tetikliyor. Kullanıcı tercihi: AI'nın çalışır durumda kalması, günlük
raporun o günler için hariç-tutulmuş görünmesinden daha öncelikli.

## Faz 268a-z + Faz 239-250 — "İsabeti artırmanın yolu daha akıllı kullanım" yol haritası (2026-08-11 — 2026-08-12)

İki ayrı yol haritası belgesi baştan sona uygulandı: önce Faz A-D (ajan-özel
confidence kalibrasyonu, rejim-farkında öğrenme, çoklu-zaman-dilimi
kademe, Kelly boyutlandırma), sonra Faz 239-250 (CMA-ES, Relative
Strength Agent, Predictive Risk, Microstructure Layer, Live A/B Testing).
Bu turun ayırt edici özelliği: her fazın yanında GERÇEK üretim
verisiyle doğrulanmış, kod değişikliğine yol açan en az bir canlı bulgu
var — hiçbiri sadece "yeni özellik ekleme" değil.

**Faz A — Ajan-özel confidence kalibrasyonu.** Önceden SADECE fused/global
confidence kalibre ediliyordu (`services/confidence_calibration.py::
compute_calibration_curve`); artık her ajanın KENDİ ham confidence'ı,
`council_orchestrator.py::deliberate()` içinde `AgentOpinion.recalculate()`
'dan ÖNCE, o ajanın kendi domain'inin gerçek geçmiş doğruluğuna göre
düzeltiliyor (`calibrate_domain_confidence`). Kanıt-sayısı yumuşatması
eklendi: `evidence_count < 3` olan kararlarda düzeltmenin büyüklüğü
`evidence_count/3` ile orantılı küçültülüyor — tek kanıtlı zayıf bir
sinyalin kalibrasyonla yapay şekilde şişmesini önlüyor (gerçek bulgu:
quant_agent'ın Hurst ölü bölgesindeki tek-kanıtlı bir SHORT'u %25'ten
%77.5'e şişirmişti).

**quant_agent Hurst ölü bölgesi.** Hurst exponent [0.45, 0.55] aralığında
("ne trend ne mean-reversion") skor hiç indirim görmüyordu — artık
volatilite indirimiyle AYNI desende `score *= 0.5`. Gerçek altın/gümüş
SHORT kayıp serisinin kök nedeniydi; bugün (2026-08-12) gerçek kayıp
işlem verisiyle yeniden replay edilip düzeltmenin işe yaradığı
doğrulandı (aynı ham feature'lar artık SHORT değil WAIT üretiyor).

**Faz B — Regime-Aware Learning.** `AgentWeightSnapshot`/`WeightApproval`
artık piyasa rejimine ("trend_volatility" formatı) göre ayrı
öğrenilebiliyor — bir rejimde iyi olan bir ajanın ağırlığı başka bir
rejimin öğrenmesini kirletmiyor. Rejim-özel veri yoksa fail-closed
global snapshot'a düşülüyor.

**Faz C — Multi-Timeframe Cascade.** Üst zaman dilimlerinde (varsayılan
15m/1h) TAM CognitiveEngine (embedding dahil) çalıştırılıp naive-Bayes
bağımsız-kanıt varsayımıyla birleştiriliyor, `timeframe_belief` olarak
ana motora enjekte ediliyor. Varsayılan kapalı (opt-in, ~3x maliyet).

**Faz D — Signal-Strength Position Sizing (Kelly).** MetaStage'in ACT
katmanı (confidence >= act_threshold) önceden confidence=0.71 ile
confidence=0.99'a AYNI (tam) boyutu veriyordu. `services/kelly_sizing.py`
artık o confidence kovasının GERÇEK kazanç/kayıp dağılımından half-Kelly
çarpanı hesaplıyor — yetersiz veride 1.0 (mevcut davranış), asla
büyütmüyor.

**Kritik üretim olayı — HuggingFace Hub donması.** Embedding modeline
giden zaman aşımsız, kimliksiz bir istek celery worker'ı (concurrency=1)
tamamen dondurmuştu — canlı sırada 8320+ görev birikti, kullanıcının
kendi backtest istekleri saatlerce sonuçsuz kaldı. `HF_HUB_OFFLINE=1`/
`TRANSFORMERS_OFFLINE=1` (model zaten yerel cache'te) + kuyruk temizliği
+ servis restart ile çözüldü.

**Faz 239-241 — Online Meta-Learning (CMA-ES).** `agents/technical_agent.py`
'nin ~12 sabit skorlama katsayısı artık `TechnicalAgentCoefficients` ile
dışarıdan verilebilir (varsayılanlar mevcut sabitlerle birebir aynı).
`meta_optimizer/agent_tuner.py`, gerçek kapanmış işlemlerin gerçek
feature'larını replay ederek CMA-ES ile bu katsayıları sentetik Sharpe'a
göre arıyor; embargo'lu walk-forward doğrulama OOS Sharpe farkı >= +0.4
şartını geçmeden bir θ insan onayına (agent_tuning_approvals, WeightApproval
ile aynı desen) dahi sunulmuyor. Haftalık celery görevi.

**Faz 242-243 — Relative Strength Agent (10. oy-veren ajan).** Bir
sembolün getirisini AYNI anda izlenen watchlist'teki diğer sembollerin
ortalama getirisiyle karşılaştırıyor. Ek ağ isteği yok — zaten
`ingest_order_book_task`'ın doldurduğu `market_snapshots`'tan okunuyor.
<3 karşılaştırma verisi varsa (ya da kripto olmayan bir sembol) dürüstçe
WAIT.

**Faz 244-246 — Predictive Risk (Regime-Switching Monte Carlo + CPPI).**
`decisions.market_regime` eklendi (yeni sütun, sadece bundan sonraki
kapanışlar için dolduruluyor). `risk/predictive/monte_carlo.py`, GERÇEK
rejim-koşullu kapanmış işlem yüzde getirilerinden (icat edilmiş bir
dağılım değil) bootstrap örneklemesiyle yakın-vadeli seri kayıp riskini
simüle ediyor; `risk/predictive/cppi.py` bu riske göre MetaStage'in
(Kelly) belirlediği boyutu CPPI mantığıyla EK olarak küçültüyor
(RiskTargetStage'den önce) — [0.25, 1.0] aralığında, asla büyütmüyor.

**Faz 247-249 — Microstructure Layer (funding rate + open interest).**
Gerçek bulgu: `exchange_gateway/binance/adapter.py::fetch_funding_rate/
fetch_open_interest` yazılmıştı ama `/fapi/...` (Binance FUTURES API)
yollarını spot'un temel URL'ine bağlı istemciyle çağırıyordu — gerçek
bir çağrı 403 Forbidden döndürüyordu, hiç çalışmamıştı. Mutlak URL ile
düzeltildi. `order_flow_agent` (zaten 9. oy-veren ajan) iki yeni sinyalle
genişletildi: funding_rate (sentiment_agent'ın positioning yorumuyla AYNI
kontrarian felsefe) ve open_interest_trend (ADX'in technical_agent'taki
rolüyle aynı desen — teyit/temkin, kendi başına yön belirlemiyor).

**Faz 250 — Live A/B Testing Framework.** `decisions.experiment_bucket`
(yeni sütun) bir kararın hangi deneyin control/treatment kovasından
geldiğini etiketliyor. Faz 233'te kaldırılan `experiment_registry`
tablosunun AKSİNE (write-only, hiç okunmayan bir denetim kaydıydı) —
`services/ab_testing.py::evaluate_experiment` GERÇEKTEN okuyor: Welch's
t-test ile control/treatment'ın gerçek pnl dağılımını karşılaştırıp
promote/rollback/insufficient_data verdict'i döndürüyor.
`multi_timeframe_cascade_ab_test_enabled` (varsayılan kapalı) açıkken
her sembol bağımsız rastgele kovaya atanıyor.

**Kritik canlı bulgu — donmuş ağırlık snapshot'ı.** `weight_history/`
içinde technical_agent'ın ağırlığı 6 Ağustos'tan beri 1.42 (matematiksel
olarak İMKANSIZ bir değer — gerçek formül asla 1.0'ı geçemez, eski/artık
kullanılmayan bir güncelleme yolundan kalma) değerinde donmuş kalmıştı;
bu değer canlı kararlara GERÇEKTEN uygulanıyordu (`belief_engine.py::
apply_weights`). Aynı zamanda bugünkü (12 Ağustos) take_profit oranı
tarihsel ~%20-37'den %0'a düşmüştü (102 stop_loss, 0 take_profit, 24
saatte) — iki bulgu zaman olarak birebir örtüşüyor. Kullanıcı düzeltme
onayını uyguladı, canlı ağırlık 1.42'den 0.776'ya düştü; etkisinin
gözlemlenmesi (~4.7 saatlik ortalama pozisyon süresi nedeniyle) devam
ediyor.

**Metodolojik not — üçüncü taraf AI rapor doğrulama disiplini.** Bu tur
boyunca kullanıcının yapıştırdığı birden fazla "AI inceleme raporu"
(PAXG/altın SHORT kayıpları, "106/106 stop-loss" istatistiksel iddiası,
confidence kalibrasyon bulguları) gerçek koda/veriye karşı doğrulandı.
Sonuç karışıktı: bazı iddialar doğru çıktı (MacroAgent'ın gerçekten
sistematik olarak yetersiz-güvenli çıktığı, ~%84.6 doğru ama %30 beyan
ettiği — ama bu ZATEN Faz A'nın düzelttiği bir durum), bazıları abartılıydı
("106/106" iddiası gerçekte 150 kapanıştan 37 kazanç/113 kayıptı, ve
sistemin kendi 1:4 stop:hedef oranı zaten bir kayıp-ağırlıklı dağılım
üretir — "yazı tura" varsayımı yanlıştı), bazıları tamamen yanlıştı
(`reverse_direction` canlı kodda hiç yok; trend hesaplama ters değil).
Prensip: her iddia gerçek sorgu/replay ile kanıtlanmadan aksiyona
dönüşmüyor.

## Faz 228-238 — öğrenme döngüsü kilidi + gerçek backtest + sinyal zenginleştirme (2026-08-07)

Faz 213-227'nin hemen ardından, kullanıcının canlı sistemi denetlerken bulduğu
kritik bir bulgudan başlayan yoğun bir tur. En önemli kararlar:

**Faz 229 — KRİTİK: ağırlık öğrenme döngüsü 7000+ bekleyen onayla fiilen
kilitlenmişti.** `WeightOptimizer.optimize()` (her gerçek trading cycle'da)
ve `propose_weights()` (her pozisyon kapanışında) büyük bir ağırlık
değişikliği hesapladığında, ZATEN bekleyen bir onay olup olmadığını hiç
kontrol etmeden koşulsuzca yeni bir `WeightApproval` satırı ekliyordu.
Canlıda doğrulandı: 6973 bekleyen onay, gerçek uygulanan ağırlıklar 2+
saattir hiç güncellenmemiş. `WeightApprovalRepository.has_pending()` dedup
kontrolü eklendi, backlog temizlendi (reddedildi, silinmedi), günlük
`auto_reject_stale_weight_approvals_task` celery beat'e eklendi.

**Faz 234 — KRİTİK: `WeightOptimizer.optimize()` tüm ajanlara aynı bloke
skoru veriyordu.** Kullanıcı canlı bir onayda 9 ajanın HEPSİNE tıpatıp
aynı +0.100 verildiğini fark etti — "doğru yolda ilerliyor gibi görünüyor
mu?" Kök neden: `decision_score` (cycle'ın TEK genel sonucu) her ajana,
o ajanın kendi yönü nihai kararla aynı mı ters mi olduğuna bakılmadan
uygulanıyordu — `position_closer.py`'nin (Faz 211b) zaten doğru
uyguladığı "ajanın KENDİ yönüne göre" ilkesi `optimize()`'a hiç
taşınmamıştı. Artık `executed_direction` parametresiyle her ajan kendi
yönüne göre ödüllendiriliyor/cezalandırılıyor.

**Faz 232 — order_book_snapshots.time yerel saatle yazılıyordu.** Yeni
sağlık kontrolünü (aşağıda) doğrularken bulundu: `age_seconds=-7146`
(negatif, gelecekte!). `BinanceAdapter.get_order_book()` naive
`datetime.now()` (CEST=UTC+2) kullanıyordu — aynı, Faz 210a'da
`contracts/context.py`'de düzeltilen bug'ın farklı bir dosyadaki tekrarı.
`datetime.now(UTC)`'ye çevrildi, gerçek DB'lerde 2160+ eski hatalı satır
temizlendi.

**Faz 236 — Backtests artık gerçek Binance geçmiş verisiyle çalışıyor.**
Eski `/backtest/run` (dashboard'un tek butonu) sabit BTCUSDT'ye kodluydu
VE `ctx.market.features`'ı hiç doldurmuyordu (`backtest/
cognitive_backtest_runner.py`'nin dokümante ettiği bir sınırlama) — ATR=0
olduğu için DecisionFusion her zaman reddediyordu, yön için gerçek
council yerine sabit bir sezgi kullanılıyordu. Tam olarak Faz 203-211'in
"ajanlar kör çalışıyor" bug'ının backtest koduna sızmış hali. Yeni
`backtest/real_historical_backtest.py` — gerçek Binance geçmişi, gerçek
signal_engine.py fonksiyonları, gerçek CognitiveEngine council'i, gerçek
stop/target çıkış simülasyonu (`position_closer.py::_exit_reason` ile
birebir aynı), maker/taker ücret ayrımı. Her adım gerçek bir
`CognitiveEngine.run()` çalıştırdığı için (dakikalar sürer) her zaman
async — `run_real_backtest_task` (celery) + `POST /backtest/run-real-async`.
`BacktestRuns.tsx` artık watchlist'ten çoklu sembol seçebiliyor, gerçek/
sahte veri modları ayrı gösteriliyor. Yan bulgu: `asyncio.run()`'ın zaten
çalışan bir event loop içinden çağrılması (aynı, `data_provider.py`'de
önceden bulunan bug) — aynı paylaşılan çözümle (`_run_coroutine_sync`)
düzeltildi.

**Faz 237 — gerçek Wyckoff olayları + Bollinger/VWAP/ADX/OBV.** Kullanıcı:
"Gerçek wyckoff analizi yaptıralım. Ekleyebileceğimiz bütün teknik analiz
yöntemlerini ekleyelim eğer matematiksel bir yöntemse." Gerçek, kesin
tanımlı Wyckoff olayları (`_wyckoff_event`): Spring (menzil desteğinin
altına sarkıp içeri kapanan sahte kırılım, bullish), Upthrust (aynısının
aynası), Sign of Strength/Weakness (hacimle doğrulanmış gerçek kırılım/
çöküş) — mevcut `structure_phase`'in (kasıtlı olarak kaba kalan genel-
rejim yaklaşıklaması) yanına eklendi. Bollinger Bands (%B, bandwidth),
VWAP sapması, ADX (Wilder, +DI/-DI — trend GÜCÜ, sistemde başka hiçbir
gösterge bunu ölçmüyordu), OBV trend + fiyat/OBV ıraksaması —
TechnicalAgent'a skorlandı. Kasıtlı olarak eklenmedi: Stochastic/Williams
%R/CCI (RSI ile örtüşüyor), Parabolic SAR/Keltner/Donchian (mevcut trend/
ATR/swing ile örtüşüyor), Ichimoku (yüksek karmaşıklık, düşük katma
değer).

**Faz 238 — kirli geçmiş veri (aşırı capital testleri) istatistiklerden
hariç tutuldu.** Kullanıcının kendi deneyleri (`starting_capital` 10-500
milyar) sırasında gerçek notional hedefi ~$1333 iken bazı işlemler $36-58
milyon'a ulaşmıştı. Satırlar SİLİNMEDİ (Class 2 prensibi) — yeni
`decisions.excluded_from_stats` kolonuyla işaretlendi (eşik: notional
>$10,000, tarih aralığı DEĞİL çünkü sane/kirli işlemler zaman içinde iç
içe geçmişti). `closed_trades_summary()`/`performance_by_period()`/
`list_closed_trades()` artık bunları filtreliyor, Performance sayfası kaç
tanesinin hariç tutulduğunu şeffafça gösteriyor.

**Diğer önemli düzeltmeler/kaldırmalar:**
- Faz 230: CI en az Faz 189'dan beri kırıktı (`quantdb_test` CI'da hiç
  oluşturulmuyordu, her push kırmızıydı, kimse fark etmemişti) — düzeltildi.
  Reddit OAuth2 sosyal medya sentiment eklendi (kullanıcının kendi ücretsiz
  hesap kaydı gerekiyor, henüz tamamlanmadı — Reddit'in kendi CAPTCHA'sında
  takıldı). `pytest-rerunfailures` (dar kapsamlı, sadece 2 bilinen imza).
  `currency_provider.py`'ye 60sn önbellek. `pyproject.toml`'daki eksik
  hatch paket listesi düzeltildi.
- Faz 231: `GET /health/signals` — zombi-sinyal izleme (candle/order-book/
  trading-cycle staleness + "son 30 karar hep WAIT" tespiti), dashboard'da
  kırmızı alarm banner'ı.
- Faz 233: Experiments özelliği tamamen kaldırıldı (her karar için git-sha
  denetim kaydı yazıyordu, hiçbir ajan okumuyordu, 4885 satır birikmişti).
- Faz 235: Live Predictions kaldırıldı (Tokens sayfasıyla birebir
  yinelemeydi, Faz 217'de zaten aynı `build_tokens_list()`'i kullanıyordu).

**Hâlâ açık, dürüstçe disclosed:** whale accumulation/exchange flow/MVRV
(gerçek ücretsiz kaynak yok), Reddit sentiment (kullanıcı tarafında
bekliyor), `reduce_threshold` vs `min_profit_target_pct` kalibrasyonu
(kullanıcıyla netleşmedi), gerçek pozitif-EV kanıtı (yeni real_historical_
backtest ile ölçülüyor, henüz uzun-vadeli sonuç yok).

**Önceki durum (v1.31.0, Faz 213-227) aşağıda korunuyor.**

## Faz 213-227 — zayıf ajanlar + ekonomi kalibrasyonu + dashboard okunabilirlik turu (2026-08-06)

Kullanıcı: "Zayıf ajanları güçlendirelim... En önemli bulgu üzerinde
çalışalım" (negatif beklenen değer / düşük kazanma oranı) ile başlayan,
sonra gerçek kullanıcı gözlemleriyle (dashboard tutarsızlıkları, ücret
şikayeti, UI özensizliği) genişleyen çok fazlı bir tur. Kullanıcıya
yönelik en kritik kararlar:

**Faz 216 — vade dolunca pozisyon kapatma TAMAMEN kaldırıldı.** Kullanıcı:
"Kazanma oranı %8... Bile bile zarar etmek demek bu. Belirli bir süre
sonunda pozisyon kapanması olayını kaldıralım hatta yasaklayalım.
Pozisyona girdiyse ya tp olacak ya da sl, başka türlü kapatılmasın."
Gerçek veriyle doğrulandı: `trade_horizon` (10dk) < `candle_timeframe`
(15dk) olduğunda kapanan işlemlerin **%64'ü** "time_expired" (stop/target'a
hiç ulaşmadan, sadece vade dolduğu için, küçük komisyon kaybıyla)
kapanıyordu — sinyal kalitesinden tamamen bağımsız, yapay bir kayıp
mekanizmasıydı. `services/position_closer.py::close_due_positions()`
artık SADECE gerçek stop_loss/take_profit fiyatına ulaşıldığında kapatıyor
(`hold_seconds`/time-expiry fallback kodu tamamen silindi). Güvenli:
`DecisionFusion`'ın Negative EV kapısı zaten stop/target'ı set edilmemiş
bir pozisyonun "open" statüsüne ulaşmasına izin vermiyor.

**Faz 221 — "Varsayılanlara dön" butonu, matematiksel olarak hesaplanmış
defaultlar.** Kullanıcı: "Komisyonlara ezilmeden 1-5 dolar arası minik
karlar getirecek bir ayar optimizasyonu yapalım, default'a basınca bunu
çağırsın otomatik." Gerçek ölçümlerle geriye doğru hesaplandı:
`capital_per_trade = starting_capital × max_capital_pct / max_concurrent_positions`
→ `50000×0.4/15 = $1333/işlem`; 15m BTCUSDT medyan 2×ATR hedefi (gerçek
ölçüm) `%0.3485`; round-trip komisyon (gerçek taker×2) `%0.1`; net kâr
(medyan durumda) `≈$3.31`. Yeni defaultlar: `max_concurrent_positions=15`,
`max_capital_pct=0.4`, `starting_capital=50000`, `trade_horizon=medium`
(4 saat — Faz 216 ile birlikte, sinyalin üretildiği mum tamamlanmadan
kapanmaması için), `min_profit_target_pct=0.0015`, `candle_timeframe=15m`.
`AppSettingsRepository.reset_to_defaults()` + `POST /settings/reset-defaults`
(watchlist/trading_mode gibi kullanıcı tercihlerine dokunmaz).

**Faz 226 — trade_horizon/candle_timeframe artık birbirine göre çapraz
doğrulanıyor.** Faz 221'in defaultları kullanıcı tarafından tekrar
uyumsuz bir kombinasyona çekilebilirdi (aynı Faz 216 bug'ına dönüş
riski) — `POST /settings/trade_horizon` ve `POST /settings/candle_timeframe`
artık `trade_horizon_seconds ≥ candle_timeframe_seconds × 2` kuralını
karşı ayara göre doğruluyor.

**Faz 214a-b — zayıf ajanlar güçlendirildi (gerçek root-cause'lar):**
- `WeightOptimizer.propose_weights()` insan-onay kapısını atlıyordu
  (`optimize()`'ın aksine) — artık ikisi de aynı `MAX_WEIGHT_DELTA`
  kontrolünü paylaşıyor.
- Hurst exponent hesaplaması `log_returns`'ün (zaten durağan) farkını
  ölçüyordu, `log(closes)`'un değil — QuantAgent bu yüzden neredeyse hep
  0 confidence veriyordu (canlı BTCUSDT: 0.0 → düzeltmeden sonra 0.345).
- `OrderFlowContext.aggressive_buy_ratio` hep sabit 0.5'ti — artık
  Binance'in gerçek son işlemlerinden (`fetch_recent_trades`,
  `isBuyerMaker`) hesaplanıyor.
- Wyckoff `structure_phase`, mutlak bir vol_ratio eşiği yerine (neredeyse
  hiç tetiklenmiyordu) kendi geçmişine göre yüzdelik dilim kullanıyor —
  gerçek veride 4/5 sembolde artık "neutral" dışı fazlar üretiyor.
- `MacroAgent`: sadece "tight" likidite cezalandırılıyordu, "loose"
  (gerçek mevcut koşul) hiç ödüllendirilmiyordu — simetri eklendi.

**Faz 219/224/227 — kullanıcı sorularına yanıt olarak yapılan denetimler:**
- **Onchain veri** ("gerçek veri geliyor mu, kaynağı nasıl artırırız?"):
  `eth_gas_price_gwei` (Infura, gerçek — canlı doğrulandı: ~0.21 gwei),
  `solana_tps` (Helius), `stablecoin_mint_24h` (USDT total supply delta),
  `network_activity_trend`/`hash_rate_trend` (blockchain.info, BTC'ye özel
  ama TÜM kripto sembollerine "genel piyasa sağlığı" göstergesi olarak
  uygulanıyor — bilinçli, `contracts/onchain.py`'de belgelendi, bkz. C).
  exchange_inflow/outflow, whale accumulation, MVRV Z-Score hâlâ icat
  edilmedi (gerçek ücretli indexer gerektiriyor). Sosyal medya sentiment
  de yapılmadı — Reddit'in genel JSON API'si artık kimliksiz erişimi 403
  ile engelliyor, kullanıcının kendi client_id/secret kaydı gerekiyor.
- **Teknik analiz** ("Fibonacci, fincan-kulp var mı?"): Fibonacci
  retracement (23.6/38.2/50/61.8/78.6%, en son swing high/low'a göre,
  gerçek yön ayrımıyla) eklendi. Cup&handle bilinçli olarak eklenmedi —
  Wyckoff'takiyle aynı dürüstlük ilkesi: kesin matematiksel tanımı yok,
  şekil-eşleme gerektiriyor.
- **İşlem ücretleri** ("kurtulma/minimize etme yolları var mı?"):
  take_profit çıkışı artık ucuz "maker" oranıyla (%0.02, gerçek borsa
  mantığı: hedefe oturmuş limit emri) ücretlendiriliyor — önceden her
  çıkış taker (%0.05) idi. stop_loss taker kalıyor (gerçek borsalarda
  tetiklenince market emrine dönüşüyor).
- **Candle lookback 1000 tavanı** ("çok yetersiz görünüyor"): gerçek
  Binance API tavanı olduğu doğrulandı (limit=1001 istense bile 1000
  döner) — `BinanceAdapter.fetch_ohlcv` artık limit>1000 için pagination
  yapıyor, tavan 5000'e çekildi. Yeni `long_term_trend_regime` göstergesi
  (gerçek 200-EMA, en az 220 bar) bu derin geçmişi gerçekten kullanan ilk
  sinyal — eski göstergelerin hiçbiri 50 bardan fazlasını kullanmıyordu.
- **İki bağımsız context kurucusu** (review bulgusu E): `services/
  orchestrator.py::_build_context()` ile `api/rest/cognitive.py::
  run_cognitive_cycle()` aynı ~70 satırı bağımsızca tekrarlıyordu (Faz
  206'nın proposed_size düzeltmesi birinde yapılıp diğerinde unutulmuştu).
  Module-level `build_cognitive_context()`'e indirildi, tek gerçek kaynak.

**Dashboard veri tutarlılığı/okunabilirlik (kullanıcı: "Transaction
dashboarduna gelen veriye güvenemiyorum", "Approvals'ın formatı çok
dağınık"):**
- `GET /trades`'in summary'si (count/win_rate/total_pnl) `limit`
  parametresine (varsayılan 100) bağlıydı — toplam kapanmış işlem 100'ü
  geçince sonsuza dek 100'de donuyordu, `GET /performance`'ın ayrı
  (limit=10000) hesabıyla tutarsızdı. Yeni `DecisionPersistor.
  closed_trades_summary()` — limitsiz tek SQL agregasyonu, ikisi de
  bunu kullanıyor.
- `Card`/`StatCard`'a `min-w-0`/`overflow-hidden`/`break-words` — uzun
  sayılar artık kutunun dışına taşmıyor.
- `PendingApprovals.tsx`: `JSON.stringify(a.proposed)` tek satırlık ham
  JSON yerine, her ajan domain'i için önceki/yeni/değişim gösteren
  gerçek bir tablo (en büyük |değişim| en üstte) + daha önce hiç
  bağlanmamış "Reddet" butonu.
- Para birimi tercihi (USD/BTC/TRY): kullanıcı "PNL hangi birimde belli
  değil... her yerde aynı problem var" dedi. `market_data/fx/
  currency_provider.py` — Binance'in kendi piyasalarından (BTCUSDT,
  USDTTRY) gerçek, canlı oranlar. `dashboard/src/lib/currency.ts::
  useCurrency()` — Performance/Transactions/Dashboard/Tokens/
  LivePredictions'daki TÜM fiyat/PnL alanlarına uygulandı.
- `LivePredictions`/`Tokens.tsx::build_tokens_list()` paylaşımı (Faz
  217) zaten var — watchlist'e yeni sembol eklenince otomatik görünüyor.
- Login kalıcılığı (Faz 218): local-only kullanım için, JWT zaten
  localStorage'da kalıcıydı ama `App.tsx` her yenilemede sıfırdan
  `isLoggedIn=false` başlatıyordu.

**Not — bu ekonomi/UI turunun ortasında biriken canlı veri:** kullanıcının
kendi deneyleri sırasında (`starting_capital` 500 milyar gibi aşırı test
değerlerine çekildi) `decisions` tablosunda gerçek ama ölçek dışı bir
dönem birikti (`deployed_notional`/`total_pnl` şu an yüz milyonlarca $
mertebesinde) — bu veri SİLİNMEDİ (gerçek geçmiş, kullanıcının onayı
olmadan silinmez), ama "all_time" agregatları bu dönemi de kapsıyor, bu
yüzden şu anki gerçek (sane defaults sonrası) performansı temsil etmiyor
olabilir.

**Önceki durum (v1.30.0, Faz 203-212) aşağıda korunuyor.**

## Faz 203-212 — "AI hiç işlem açmıyor" zincirinin tamamı (7 katmanlı, birbirine bağlı bug)

Kullanıcının "dünden beri hiç işlem almamış" şikayetiyle başlayan derin
inceleme, tek bir sebep değil, art arda dizilmiş 7 bağımsız sessiz-hata
katmanı buldu (hiçbiri exception atmıyordu, hepsi "boş/nötr" sonuç
üretiyordu — test coverage bunları yakalamamıştı çünkü hepsi gerçek uçtan
uca veri akışı gerektiriyordu):

1. **Faz 203** — `Metacognition.evaluate_confidence()`, Council'in gerçek
   ağırlıklı konsensüs gücünü (`belief.strength`) hiç kullanmıyordu, sadece
   hafızaya bakıyordu (hafıza yoksa sabit 0.5). *(Not: bu bulgunun "entropy
   kullanılıyordu" şeklinde bir dış özeti dolaştı — bu YANLIŞ, kodda entropy
   hiç geçmiyor; gerçek sorun confidence'ın hafıza-dışı hiçbir sinyal
   kullanmamasıydı.)*
2. **Faz 205** — `BeliefEngine.apply_weights()`, güvenilirliği düşük
   ajanları "bench" eden (`performance_weight=0`) mekanizmayı eski bir
   weight snapshot'ıyla sessizce eziyordu (overwrite yerine çarpım
   gerekiyordu) — WAIT %100 baskın çıkıyordu.
3. **Faz 206** — `proposed_size` üretim yolunda hiç set edilmiyordu (hep
   0), MetaStage'in ACT dalı `final_size`'ı hiç yazmıyordu — onaylanan bir
   ACT kararı bile hiçbir zaman pozisyon açamıyordu.
4. **Faz 207** — Mum verisi ingestion'ı (`ingest_candles_task`) hiç
   zamanlanmıyordu, Market sayfası BTC dışında hep boştu.
5. **Faz 208** — Test modunda `reduce_threshold` neredeyse sıfıra
   indirildi (0.05) — zayıf ama gerçek sinyaller artık denenebiliyor.
6. **Faz 210a** — `contracts/context.py` naive `datetime.now()` (yerel
   CEST) kullanıyordu, `position_closer.py` `datetime.now(UTC)` — aynı
   satırda ~2 saatlik fark, kapanış açılıştan önce görünüyordu.
7. **Faz 210b/211b** — Gerçek kapanan pozisyonların sonucu hiçbir zaman
   `AgentMemory`/`WeightOptimizer`'a geri beslenmiyordu (tetikleyici
   scheduler hiç başlatılmıyordu, ayrıca `agent_opinions=[]` ile kırıktı).
   Artık her kapanışta ajanların KENDİ yönüne göre (işlemin genel
   kârlılığına göre değil) doğruluk kaydediliyor.
8. **Faz 210c** — İlk gerçek kapanan işlemler hedefe ulaştı ama komisyon
   kârı yedi (`min_profit_target_pct` eklendi, varsayılan %0.5).
9. **Faz 211a** — Pozisyon büyüklüğü fiyattan bağımsız "1.0 birim"
   öneriyordu (PAXGUSDT $4275 notional vs ADAUSDT $0.19 notional aynı
   "size"). Artık sermaye bütçesi/fiyat = birim sayısı.
10. **Faz 211c** — Ölü kod temizliği: `MetaLearner` (fiilen işlevsizdi,
    `threshold_optimizer.py` gerçek yerini aldı), `PendingOutcomeTracker`
    (hiç başlatılmıyordu), `OutcomeTracker.attach_outcome()` silindi.
11. **Faz 212** — `DecisionFusion`'ın ret gerekçesi (Negative EV /
    min_profit_target_pct) `decisions.agent_contributions`'a hiç
    yazılmıyordu — artık kalıcı, "neden reddedildi?" sorusu DB'den
    cevaplanabiliyor.

**Bilinen, henüz çözülmemiş gerilim:** Faz 208 (reduce_threshold≈0) daha
çok zayıf sinyalin denenmesine izin veriyor, Faz 210c (min_profit_target_pct
%0.5) bunların çoğunu ATR-tabanlı hedef fiyatın %0.5'ini geçmediği için
eliyor — gerçek veride 30 yönlü sinyalden sadece 3'ü açılabildi. Bu iki
ayarın birlikte kalibrasyonu kullanıcıyla henüz netleşmedi.

**Önceki durum (v1.24.0, Faz 187-200) aşağıda korunuyor.**

## Faz 200 — bilinçli olarak yapılmayan trading teknikleri (dürüst sınır)

Proje sahibi "hiçbir yönden eksik kalmasın" isteğiyle opsiyon stratejileri,
Elliott Wave, Gann, istatistiksel arbitraj/pairs trading sordu. Pairs
trading gerçekten inşa edildi (Faz 200 — statsmodels ile gerçek Engle-
Granger kointegrasyon testi). Diğer ikisi BİLİNÇLİ OLARAK yapılmadı:

- **Elliott Wave**: Dalga sayımı büyük ölçüde sübjektif — profesyonel
  analistler aynı grafikte farklı sayım yapar, kesin tanımlı bir algoritma
  yok. Kodda "kesin" bir tespit yapılamaz, olsa olsa kaba bir zikzak/pivot
  tespiti olurdu (structure_phase/Wyckoff'ta zaten yapılan basitleştirme
  gibi) — katma değeri şüpheli, sahte sofistikasyon riski gerçek.
- **Gann açıları/kareleri**: Kuant camiada büyük ölçüde pseudo-bilimsel
  kabul ediliyor (fiyat-zaman simetrisi varsayımının matematiksel/istatistiksel
  bir temeli kanıtlanmamış). Bunu inşa etmek bu oturumun baştan beri
  kaçındığı "sahte sofistikasyon" tuzağı olurdu.
- **Opsiyon stratejileri**: Sistem şu an sadece spot (anlık alım-satım)
  işlem yapıyor. Opsiyon eklemek yeni bir veri kaynağı (opsiyon zinciri),
  yeni bir fiyatlama modeli (Black-Scholes, Greeks) ve yeni bir risk modeli
  gerektirir — teknik olarak yapılabilir ama bugünkü işin kat kat üstünde
  bir kapsam, ayrı bir proje olarak planlanmalı. Şimdilik yapılmadı.

Bu üçü proje sahibiyle konuşulup onaylandı — "eksik" değil, bilinçli kapsam
kararı.

## Faz 189 — testler artık gerçek dev DB'ye asla yazmıyor (kritik altyapı düzeltmesi)

**Bulgu:** Tüm test suite (400+ test) `SessionFactory` üzerinden AYNI gerçek
geliştirme veritabanına (`quantdb`) yazıyordu — dashboard'un baktığı DB ile
birebir aynı. Bu, oturum içinde ÜÇ AYRI kullanıcı-görünür yerde gerçek
bozulmaya sebep oldu: Experiments listesi rastgele test sembolleriyle
doluyordu, yeni Transactions sayfası "%100 kazanma oranı" gibi anlamsız
veri gösteriyordu (test'in kendi ürettiği sahte `entry_price=100` vs gerçek
piyasa fiyatı ~50000 farkından), ve bir test çalıştırması sessizce
`app_settings`teki `trading_mode`'u `live`'a çevirebiliyordu.

**Düzeltme:** Kök `conftest.py` — pytest herhangi bir test modülünü import
etmeden önce `DATABASE_URL_SYNC`/`DATABASE_URL`/`TIMESCALE_URL`'i ayrı bir
`quantdb_test` veritabanına çeviriyor (`config.get_settings()` `@lru_cache`
olduğu için bunun tüm app import'larından ÖNCE olması şart). `quantdb_test`
gerçek migration zincirinin tamamıyla (`alembic upgrade head`) kuruldu.

**Bu izolasyon iki gerçek, önceden gizli bug'ı ortaya çıkardı** (migration'lar
dışında hiç dokunulmamış taze bir DB'de her ikisi de anında patladı):
1. `EpisodeRepository.save()` / `ObservationRepository.save()` hiçbir zaman
   `created_at` set etmiyordu — migration'da `nullable=False`, server_default
   yok. Gerçek dev DB'de sadece şans eseri (elle/dışarıdan eklenmiş
   `DEFAULT now()` şema kayması) çalışıyor gibi görünüyordu. Artık kod
   tarafında açıkça `datetime.now(UTC)` set ediliyor.
2. `experiments` tablosu (curiosity engine, faz166'daki `experiment_registry`
   ile karıştırılmamalı) hiçbir migration'da tanımlı değildi — yine sadece
   gerçek dev DB'de dışarıdan var olduğu için hiç fark edilmemişti. faz189
   migration'ı `CREATE TABLE IF NOT EXISTS` ile hem taze DB'de hem mevcut
   ghost table'lı dev DB'de güvenle çalışıyor.

**Bir kerelik temizlik:** `quantdb`'deki `decisions` (8917 satır, ezici
çoğunluğu test sembolleri/varsayılan BTCUSDT test verisi) ve
`experiment_registry` (5016 satır) tabloları TRUNCATE edildi — hiçbiri
gerçek bir işlemi temsil etmiyordu (Execution Layer hâlâ yok, Transactions
özelliği bu oturumda yeni kuruldu). `app_settings` gerçek varsayılanlara
(`trading_mode=test`, `starting_capital=10000`) sıfırlandı.

## Faz 187-188 — gerçek pozisyon yaşam döngüsü + kullanıcı risk ayarları

- `decisions` artık gerçek `entry_price/exit_price/quantity/opened_at/
  closed_at` kolonlarına sahip. `services/position_closer.py` açık
  pozisyonları GERÇEK zaman geçtikten sonra GERÇEK güncel fiyatla kapatıyor
  (önceki `ForwardOutcome` anlık backtest-tarzı hesaplamasından ayrı — o hâlâ
  var ama artık sadece learning_loop/memory_engine'in öğrenme sinyali,
  kullanıcıya gösterilen "gerçek işlem sonucu" değil).
- `app_settings` (yeni tablo) + `api/rest/settings.py`: `trading_mode`
  (test/live), `max_concurrent_positions`, `max_capital_pct`,
  `starting_capital`, `trade_horizon` (kısa/orta/uzun → hold_seconds),
  `min_seconds_between_trades` (cooldown, mod'dan bağımsız uygulanır),
  `ai_enabled` (dashboard Start/Stop — kapalıyken yeni pozisyon açılmaz,
  mevcut açık pozisyonlar etkilenmez).
- `RiskEngine` + `RiskGateStage`: `AI_STOPPED`/`COOLDOWN_ACTIVE` her modda
  uygulanır; `trading_mode=test` iken geri kalan tüm kontroller (pozisyon
  sayısı, sermaye %'si, mevcut limit kontrolleri) tamamen atlanır.
- Dashboard: Transactions (açık pozisyonlar + kapanmış işlemler + PnL
  özeti) ve Settings (belirgin Start/Stop + Test/Live düğmeleri + limit
  formları) sayfaları eklendi. AI Reasoning (Ollama LLM explainer) sayfası
  kaldırıldı — hardcoded demo payload'ıyla çalışıyordu, gerçek bir karara
  hiç bağlı değildi.

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
