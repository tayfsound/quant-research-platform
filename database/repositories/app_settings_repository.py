"""Faz 188: uygulama ayarları (trading_mode, risk limitleri vb.) — tek
key-value kaynağı. risk_limits (faz172) tablosundan kasıtlı olarak ayrı:
o hash-imzalı, sayısal risk eşikleri için (max_position_size, max_drawdown);
bu, daha genel operasyonel ayarlar için (mod anahtarı gibi string değerler
de içeriyor)."""
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.orm import Session

from database.base import Base

DEFAULTS: dict[str, str] = {
    "trading_mode": "test",
    # Faz 215: kullanıcı isteği — "default ayarda sistem minik limitlerle
    # minik getiriler getirecek şekilde matematiksel olarak mantıklı bir
    # ayar, komisyonlara ezilmeden $1-5 arası net kâr." Gerçek ölçülen
    # verilerle geriye doğru hesaplandı:
    #   capital_per_trade = starting_capital * max_capital_pct / max_concurrent_positions
    #   50000 * 0.4 / 15 = $1333/işlem
    #   15m BTCUSDT medyan 2xATR hedefi (gerçek ölçüm): %0.3485
    #   round-trip komisyon (gerçek taker_rate*2): %0.1
    #   net kâr (medyan durumda) = 1333 * (0.003485 - 0.001) ≈ $3.31
    # Değişken piyasa koşullarında kesin $1-5 garantisi yok (gerçek
    # piyasa, uydurma bir sayı değil) ama temsili durumda aralığın
    # ortasına düşecek şekilde hesaplandı.
    "max_concurrent_positions": "15",
    "max_capital_pct": "0.4",
    "starting_capital": "50000",
    # Faz 215: kritik bulgu — gerçek canlı veride (289 kapanan işlem)
    # %64'ü "time_expired" (stop/target'a hiç ulaşmadan sadece vade
    # dolduğu için, küçük komisyon kaybıyla kapanmış) çıktı. Sebep:
    # trade_horizon="short" (10 dk) < candle_timeframe="15m" (15 dk) —
    # pozisyon, sinyalin üretildiği mum bile TAMAMLANMADAN kapanıyordu,
    # ATR-tabanlı stop/target'ın (15m verisinden hesaplanan, gerçekçi
    # fiyat hareketi ölçeği) tetiklenmesine hiç fırsat kalmıyordu — bu
    # da kazanma oranını yapay olarak (sinyal kalitesinden bağımsız)
    # düşürüyordu. "medium" (4 saat = 16x 15dk mum), stop/target'a
    # gerçekten ulaşma şansı bırakıyor.
    "trade_horizon": "medium",
    # Faz 189: "stopsuz işlem yapmasın test modunda bile olsa" — aynı sembol
    # için art arda iki işlem açılışı arasında zorunlu minimum bekleme.
    "min_seconds_between_trades": "60",
    # Faz 190: dashboard'daki Start/Stop düğmesi. "false" iken AI yeni
    # pozisyon AÇMAZ ama mevcut açık pozisyonlar (PositionCloser) tamamen
    # bağımsız çalışmaya devam eder — hedefine ulaşan/vadesi dolan pozisyon
    # yine kapanır. Varsayılan "true" (önceki davranışla aynı, regresyon yok).
    "ai_enabled": "true",
    # Kill switch — gerçek olay (2026-08-12): 24 saatte 102 ardışık
    # stop-loss (donmuş bir ağırlık snapshot'ının kök nedeniyle), hiçbir
    # otomatik durdurma mekanizması yoktu. Bu eşiğe ulaşınca (tüm
    # semboller genelinde, en son kapanmış işlemlerden geriye doğru
    # ardışık kayıp sayısı) RiskEngine ai_enabled'ı GERÇEKTEN false'a
    # çeker — dashboard'daki manuel Start/Stop düğmesiyle AYNI kalıcı
    # etki, insan tekrar açana kadar sürer. "0" = devre dışı (icat
    # edilmiş bir varsayılan eşik dayatılmıyor, kullanıcı açıkça
    # belirlemeli) — ama gerçek olayın hemen ardından makul, muhafazakâr
    # bir varsayılan olarak 10 seçildi.
    "kill_switch_consecutive_losses": "10",
    # Faz 268-sonrası: gerçek olay (2026-08-13) — bir ağırlık rejimi
    # (technical_agent=1.42, 8 gün boyunca sabit) DEĞİŞTİRİLDİKTEN sonra
    # bile, o eski rejimle açılmış 700+ pozisyonluk bir kuyruk günler
    # boyunca kapanmaya devam etti. Ardışık-kayıp sayacı KAPANMA sırasına
    # bakıyor, AÇILMA zamanına değil — yani manuel "Başlat" her
    # basıldığında, kırılmamış eski seri (44) bir sonraki döngüde anında
    # tekrar tetikliyordu; kullanıcının "çalıştır dediğimde çalışması
    # lazım" bulgusu tam olarak buydu. Bu ayar (ISO datetime string, boş="
    # devre dışı") set edildiğinde, SADECE kill switch'in ardışık-kayıp
    # sayacı bu tarihten ÖNCE açılmış pozisyonları YOK sayıyor — dashboard
    # istatistikleri (win rate/PnL/TP-SL sayıları) ETKİLENMİYOR, o eski
    # işlemler hâlâ gerçek ve hâlâ sayılıyor, sadece "AI şu an duruyor mu"
    # kararı güncel karar kalitesine bakıyor. bkz. services/risk_state.py.
    "kill_switch_legacy_cutoff_at": "",
    # Faz 268-sonrası — kullanıcı isteği: SourceReliabilityAgent'ın
    # "reliability"i (eskiden ajanın kendi bildirdiği confidence'ın
    # ortalamasıydı, GERÇEK isabet oranı değil — hatta 120 saniyede bir
    # sıfırlanan bir in-process dict'te tutuluyordu) gerçek, kalıcı
    # (AgentMemory) isabet oranına geçirildiğinde, "başlangıç olarak her
    # ajanın kararda eşit ağırlığı olsun" istendi. kill_switch_legacy_
    # cutoff_at ile AYNI Class 2 deseni (ISO datetime string, boş="devre
    # dışı"): bu tarihten ÖNCEKİ kayıtlar reliability hesabına HİÇ
    # girmiyor — hiçbir satır silinmiyor, sadece yeni/doğru mekanizma
    # sıfırdan, adil bir başlangıç yapıyor. bkz. agents/source_
    # reliability_agent.py.
    "reliability_legacy_cutoff_at": "",
    # Faz 268-sonrası — gerçek olay (2026-08-13): XAUTUSDT'de aynı anda
    # 54 tane SHORT pozisyon açık kalabilmiş — max_concurrent_positions
    # TOPLAM sayıya bakıyor, aynı sembol/yön kombinasyonuna hiç. ENB ve
    # Cross-Symbol Correlation Filter de sadece aynı cycle'daki eşzamanlı
    # önerilere bakıyor, saatler içinde BİRİKEN aynı-yönlü pozisyonu
    # görmüyor. "0"/boş = devre dışı (icat edilmiş bir varsayılan eşik
    # dayatılmıyor) — ama gerçek olayın hemen ardından muhafazakâr bir
    # varsayılan olarak 5 seçildi.
    "max_open_positions_per_symbol_direction": "5",
    # Faz 268-sonrası — kritik bulgu: Faz 261'in 1:4 oranı (STOP=2.5x,
    # TARGET=10.0x günlük ATR) kendi yorumunda "eski/gürültülü veriden,
    # yeterli temiz veri birikince yeniden değerlendirilecek" diye
    # işaretlenmişti. Gerçek OOS doğrulaması (2026-08-13, DEFAULT_LOOKBACK
    # düzeltmesinden SONRA, 1312 gerçek işlem, %70/%30 train/test):
    # test setindeki 384 işlemin TAMAMI (bull/bear/transition rejimlerinin
    # hepsinde) stop_loss ile kapandı — ortalama MFE (%0.38) ortalama
    # |MAE|'nin (%1.28) çok altında kaldığı için TARGET_ATR_MULT=10.0'a
    # hiçbir zaman ulaşılamıyordu. Train'den (918 işlem) bulunan gerçek
    # ampirik en iyi oran ~1:0.545 (sl_pct=%1.80, tp_pct=%0.98) — STOP_
    # ATR_MULT SABİT tutulup (bilinen/kabul edilmiş risk mesafesi) SADECE
    # TARGET_ATR_MULT bu oranla yeniden ölçeklendi: 2.5 * 0.545 ≈ 1.4.
    # DSR henüz "genuinely_skillful" eşiğini (0.95) geçmiyor (0.012,
    # 65 örneklem) — yön güçlü ama istatistiksel kanıt henüz tam değil,
    # bu yüzden RiskTargetStage'e SABİT değil, AYARLANABİLİR olarak
    # bağlandı (bkz. o dosyadaki not) — veri birikince kolayca yeniden
    # kalibre edilebilir, redeploy gerekmez.
    "stop_atr_mult": "2.5",
    "target_atr_mult": "1.4",
    # Faz 268-sonrası — gerçek bulgu: trade_type'a göre ayrılmış kapanmış
    # işlemlerde "scalp" (stop < %4.5, api/rest/positions.py::_SCALP_MAX_
    # STOP_PCT ile AYNI eşik) TEK BAŞINA toplam zararın %92'siydi (-$1954/
    # -$2129), diğer türlerin (gün_içi/swing/orta_vadeli) hepsi kârdaydı.
    # RiskTargetStage artık hesaplanan stop bu tabanın altına düşerse SL/
    # TP'yi ORANI KORUYARAK genişletiyor (asla daraltmıyor).
    "min_stop_pct": "0.045",
    # Faz 269-sonrası — kullanıcı bulgusu: pump_fade_v1 (5x kaldıraçlı,
    # az likit/pompalanmış coinlerde SHORT) pozisyonları, stop'u girişe
    # çekmek için gereken TAM 1R (|entry-stop|) mesafeye ulaşmadan —
    # gerçek veride sadece %1-1.8 lehte gidip — ters dönüp likidasyona
    # kadar gitti (bkz. services/position_closer.py::_apply_breakeven_
    # stop). 60sn'lik kontrol aralığında oynak bir coin hem stop'u hem
    # likidasyonu tek sıçramada aşabiliyor. Eşik düşürüldü: artık TAM
    # 1R değil, bu oranın (varsayılan %50) kadar lehte gidiş yeterli —
    # koruma daha erken devreye giriyor, riski azaltıyor. 1.0 = eski
    # davranış (tam 1R), asla >1.0 olmamalı (stop'u girişten daha kötü
    # bir noktaya erken çekmiş olur).
    "breakeven_trigger_r_multiple": "0.5",
    # Faz 269-sonrası — kullanıcı bulgusu: pump_fade pozisyonları ~$2k
    # kârdayken piyasa tersine dönüp ~-$2k zarara kadar gidebiliyordu —
    # breakeven (yukarıdaki) TEK BAŞINA yetersiz, çünkü SADECE net zararı
    # önlüyor, GERÇEK kârı hiç KİLİTLEMİYOR (girişe çekilen stop yine de
    # $0 sonuç demek). services/position_closer.py::_apply_breakeven_stop
    # artık buna ek olarak entry_price'a göre SABİT yüzdelik bir trailing
    # stop da uyguluyor — fiyat lehte gittikçe stop arkadan takip eder,
    # SADECE gerçek kâr bölgesinde (breakeven'in ÖTESİNDE) devreye girer.
    # 0.0 = trailing kapalı (sadece breakeven). Varsayılan %5 — min_stop_pct
    # (%4.5) tabanıyla tutarlı, redeploy gerekmeden ayarlanabilir.
    "trailing_stop_distance_pct": "0.05",
    # Faz 282 — kritik bulgu (2026-08-19, kullanıcı: "kardayken -4k dolar
    # zarar yazmaya başladıysa çok mantıksız"): yukarıdaki breakeven_
    # trigger_r_multiple/trailing_stop_distance_pct, pump_fade_v1'in SABİT
    # geniş stop mesafesine (pump_fade_stop_distance_pct=%30) göre ORANTILI
    # hesaplanıyor — %50 tetikleme oranı bile %15'lik (0.5*%30) mutlak bir
    # eşik demek. Gerçek veri (7 açık pozisyon, 2026-08-19): hepsi gerçek
    # kâra geçti (MFE %0.4-%5.0) ama HİÇBİRİ ne %15 breakeven eşiğine ne de
    # %5 trailing eşiğine ulaşamadı — koruma fiilen hiç devreye giremedi,
    # hepsi kârdan zarara döndü. pump_fade_v1 için artık entry_price'a göre
    # AYRI, MUTLAK yüzdelik eşikler kullanılıyor (stop mesafesiyle orantılı
    # DEĞİL) — bkz. services/position_closer.py::_apply_breakeven_stop.
    # Diğer (AI konseyi) pozisyonlarının davranışı DEĞİŞMEDİ.
    "pump_fade_breakeven_trigger_pct": "0.01",
    "pump_fade_trailing_stop_distance_pct": "0.007",
    # Drawdown-Based Position Sizing (gambler's ruin koruması) — kill
    # switch'in kullandığı AYNI gerçek ardışık kayıp sayacıyla, sert
    # durmadan ÖNCE devreye giren kademeli bir fren. 3. ardışık kayıptan
    # itibaren, 10.'ya (kill switch'in kendi varsayılanıyla aynı, ama
    # bağımsız ayarlanabilir) kadar doğrusal olarak boyut küçülür.
    "drawdown_sizing_start_after_losses": "3",
    "drawdown_sizing_full_reduction_at_losses": "10",
    # Faz 194: AI'ın sürekli izlediği/işlem yapabildiği enstrümanlar —
    # kripto (Binance) + endeks/emtia/hisse (Yahoo Finance). Nasdaq/S&P500
    # ayrıca crypto sembollerine korelasyon sinyali olarak da besleniyor
    # (bkz. agents/technical_agent.py).
    # Faz 202: kullanıcı isteğiyle piyasa değeri/hacmi yüksek 3 kripto daha
    # eklendi (BNB, XRP, ADA — hepsi gerçek Binance USDT çiftleri).
    # PAXGUSDT/XAUTUSDT: gerçek altın-destekli kripto tokenlar (Binance'te
    # işlem görüyor, 24/7 — GC=F'nin CME saatleriyle sınırlı olmasının
    # tersine) — kullanıcı isteğiyle eklendi.
    # Faz 268-sonrası: kullanıcı isteği — "shit coin olmamalı, piyasada
    # değeri olan coinler." Gerçek Binance 24s hacim verisine göre seçildi,
    # ama ham hacim sıralaması tek başına güvenilir bir filtre değil (yeni/
    # spekülatif listelemeler de yüksek hacim gösterebiliyor) — sadece
    # yıllardır var olan, gerçek kullanım/likiditesi kanıtlı, büyük
    # borsalarda köklü projeler eklendi: DOGE (en likit meme-kökenli,
    # geniş borsa desteği), TRX (Tron — gerçek USDT settlement hacmi),
    # LINK (Chainlink — oracle altyapısı, DeFi'de yaygın), UNI (Uniswap —
    # lider DEX), NEAR (Near Protocol — köklü L1), ZEC (Zcash — 2016'dan
    # beri var, gizlilik odaklı köklü proje).
    # Faz 268-sonrası — kullanıcı isteği: "az token var artıralım... işlem
    # sayısını artıracaksak coinleri artıralım." 17 likit Binance Futures
    # paritesi eklendi (hepsi gerçek API ile TRADING durumu doğrulandı).
    #
    # Faz 268-sonrası (2) — gerçek olay: bu 37'lik liste bir ara GEÇİCİ
    # olarak hacme göre otomatik seçilen 200 sembole çıkarıldı — ama üç
    # gerçek, ölçülmüş sorun ortaya çıktı: (1) ham hacim sıralaması meme/
    # çöp coin'leri de içeri çekti (TRUMPUSDT, FARTCOINUSDT, hatta Çince
    # karakterli joke token'lar), (2) run_trading_cycle_task (120sn'de bir,
    # tek worker) 207 sembolü sırayla işlerken süresi 120sn'yi katlayarak
    # aştı, celery kuyruğu 11.900+ göreve kadar tıkandı, hiçbir backtest
    # asla sırasına gelemedi, (3) _apply_portfolio_fusion()'ın sabit
    # portföy VaR bütçesi artık onlarca eşzamanlı yönlü öneriye
    # bölünüyordu — hedef $80-100'lük pozisyonlar kuruşa (~$0.0007
    # notional) düşüyordu. Watchlist elle doğrulanmış, köklü 43 kripto +
    # 7 hisse/emtia/endekse (toplam 50) geri çekildi — kullanıcı tercihi.
    "watchlist": "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT,ADAUSDT,XAUTUSDT,DOGEUSDT,TRXUSDT,LINKUSDT,UNIUSDT,NEARUSDT,ZECUSDT,AVAXUSDT,DOTUSDT,LTCUSDT,ATOMUSDT,APTUSDT,ARBUSDT,OPUSDT,SUIUSDT,INJUSDT,FILUSDT,ETCUSDT,ICPUSDT,BCHUSDT,WLDUSDT,TIAUSDT,SEIUSDT,RENDERUSDT,AAVEUSDT,ONDOUSDT,LDOUSDT,CRVUSDT,GALAUSDT,SANDUSDT,AXSUSDT,CHZUSDT,CAKEUSDT,ALGOUSDT,XLMUSDT,VETUSDT,JUPUSDT,AAPL,NVDA,MSFT,GC=F,SI=F,^IXIC,^GSPC",
    # Faz 199: portfolio_fusion.py'nin gerçekten bağlanması — aynı cycle'da
    # birden fazla sembol eşzamanlı yönlü öneri üretirse, gerçek kovaryans
    # matrisiyle hesaplanan portföy VaR'ı bu yüzdeyi (sermayenin) aşarsa
    # önerilen büyüklükler orantılı olarak küçültülür.
    "max_portfolio_var_pct": "0.1",
    # Faz 204: MetaStage'in ACT/REDUCE/WAIT eşikleri — projenin ilk
    # commit'inden beri hiç değişmemiş, hiç gerekçelendirilmemiş
    # varsayılanlar (%70/%40). services/threshold_optimizer.py yeterli
    # gerçek kapalı işlem birikince (min. 20) bunları GERÇEK kâr/zarar
    # geçmişine göre kendi kendine güncelliyor; o zamana kadar bu
    # varsayılanlar kullanılıyor.
    "act_threshold": "0.7",
    "reduce_threshold": "0.4",
    # Faz 210: kullanıcı bulgusu — ilk gerçek kapanan iki işlem (PAXGUSDT,
    # XAUTUSDT) gerçekten take_profit hedefine ulaştı ama net PnL yine de
    # eksiye düştü, çünkü RiskTargetStage'in ATR-tabanlı hedefi (2x ATR)
    # bu fiyat seviyesinde (~4270) round-trip komisyona (~%0.1) kıyasla
    # çok küçüktü (%0.07).
    #
    # Faz 214: gerçek geçmiş veriyle backtest edince (bkz. commit mesajı)
    # %0.5'in KATASTROFİK derecede yanlış kalibre olduğu ortaya çıktı —
    # 1m mumda BTCUSDT'nin 2x ATR hedefi medyan %0.036 (%0.5'in ~14 katı
    # altında), yani gerçek Binance verisiyle 133 yönlü sinyalin
    # TAMAMI reddediliyordu, hiç işlem açılamıyordu. Gerçek ölçüm: 5m
    # mumda BTCUSDT medyan hedef %0.147 — round-trip komisyonu (~%0.1)
    # rahat aşıyor. Bu yüzden hem candle_timeframe varsayılanı 5m'e
    # çekildi (aşağıda) hem de bu eşik gerçek round-trip komisyonun
    # hemen üstüne (%0.1) indirildi — "hedefi tutturmak zaten net kâr
    # demek" ilkesini koruyor ama artık gerçek sinyalleri boğmuyor.
    # Faz 215: gerçek round-trip komisyonun (%0.1) hemen üstüne, 15m'nin
    # gerçek medyan hedefinin (%0.3485) rahatça altında — hedefi
    # tutturan işlemlerin çoğu gerçekten net kâr etsin diye.
    "min_profit_target_pct": "0.0015",
    # Faz 215: 5m'de fiyat hareketi komisyonu zar zor karşılıyordu (net
    # kâr çok küçük kalıyordu); 1d çok yavaş (günde ~1 sinyal). 15m gerçek
    # ölçümde ikisi arasında iyi bir denge — hem makul sıklıkta sinyal
    # hem komisyonu rahat aşan hedef büyüklüğü.
    "candle_timeframe": "15m",
    "candle_lookback": "100",
    # Faz 224: kullanıcı bulgusu — "PNL de para birimi görünmüyor bu hangi
    # birimle kayıp belli değil dolar mı btc mi vs... her yerde aynı
    # problem var." Sistemdeki tüm fiyat/PnL alanları zaten USD cinsinden
    # hesaplanıyor (kripto çiftleri USDT'ye endeksli, USDT~USD; hisse/
    # endeks zaten USD) — bu sadece GÖRÜNTÜLEME tercihi, hesaplamalar
    # değişmiyor.
    "display_currency": "USD",
    # Faz 255: kullanıcı isteği — "olay kaldıraçta zaten asıl olay o."
    # Token bazlı kaldıraç — JSON dict, {"BTCUSDT": 10, "XAUTUSDT": 25}
    # gibi. Watchlist'te olup burada anahtarı olmayan bir sembol 1.0x
    # (spot, kaldıraçsız) sayılır — fail-closed varsayılan, kaldıraç
    # sadece kullanıcı AÇIKÇA bir sembol için ayarlarsa devreye girer.
    "symbol_leverage": "{}",
    # Faz 259: kullanıcı isteği — "predictions WAIT döndüğünde uygun
    # zamanda ai büyük pozisyonlara girsin, orta vadeli, günler/haftalar
    # sürecek." Kısa-vadeli katmandan (candle_timeframe/max_capital_pct)
    # TAMAMEN AYRI bir sermaye havuzu ve kendi sinyal zaman dilimi —
    # ikisi aynı kapasiteyi paylaşmasın diye (bkz. services/risk_state.py).
    "medium_term_enabled": "false",
    # Kullanıcı: "böyle bir fırsat yakaladığında kasanın %10'unu
    # kullanabilsin" — kısa-vadelinin max_capital_pct'inden (0.4) bağımsız.
    "medium_term_capital_pct": "0.10",
    # Kullanıcı kararı: "ayrı günlük/4 saatlik analiz katmanı kur" —
    # kısa-vadelinin candle_timeframe'inden bağımsız, kendi sinyal
    # zaman dilimi. Günlük varsayılan: en sakin/en az gürültülü sinyal.
    "medium_term_timeframe": "1d",
    "medium_term_max_concurrent": "5",
    # Faz 268c — "İsabeti artırmanın yolu daha akıllı kullanım" yol
    # haritasının Faz C'si (Multi-Timeframe Cascade). Kullanıcı kararı:
    # raporun önerdiği TAM versiyon (üst zaman dilimlerinde de gerçek
    # CognitiveEngine çalıştırılıyor, embedding dahil) — bu, canlı
    # cycle'ı sembol başına ~3 katına çıkarabilir. Varsayılan kapalı
    # (medium_term_enabled ile aynı opt-in desen) — kullanıcı kaynak/
    # gecikme etkisini gördükten sonra açıp kapatabilsin.
    "multi_timeframe_cascade_enabled": "false",
    "multi_timeframe_cascade_timeframes": "15m,1h",
    # Faz 250: Live A/B Testing Framework. Açıksa multi_timeframe_cascade_
    # enabled'ın statik açık/kapalı anahtarı yerine, HER sembol/cycle
    # bağımsız olarak rastgele control (cascade kapalı)/treatment (cascade
    # açık) kovasına atanır ve decisions.experiment_bucket'a etiketlenir —
    # services/ab_testing.py::evaluate_experiment gerçek kapanmış
    # işlemlerle Welch's t-test karşılaştırması yapabilsin diye.
    # Varsayılan kapalı — opt-in, mevcut davranış hiç değişmez.
    "multi_timeframe_cascade_ab_test_enabled": "false",
    # Faz 268-sonrası — kullanıcı isteği: Adaptive Barrier Engine'i
    # (analytics/adaptive_barrier_engine.py, MAE/MFE'nin GERÇEK koşullu
    # dağılımından türetilen SL/TP önerisi) RiskTargetStage'e wire
    # edelim. Kullanıcı kararı: ayrı bir "açık/kapalı" anahtarı bırakma
    # ("kesin unuturum") — gerçek güvenlik zaten anahtardan değil, veri
    # şartından geliyor (build_and_save_barrier_table MIN_TOTAL_SAMPLES=
    # 200 gerçek kapanış birikmeden HİÇBİR tablo üretmiyor/kaydetmiyor,
    # tablo yoksa RiskTargetStage her zaman statik ATR hesabına düşüyor).
    # Bu yüzden varsayılan AÇIK — kendi kendine, veri birikince devreye
    # girecek (bkz. services/tasks.py::refresh_barrier_table_task).
    "adaptive_barrier_enabled": "true",
    # Faz 269-sonrası — 3. taraf inceleme bulgusu: adaptive_barrier_enabled
    # AÇIK olduğu için, barrier tablosu ilk kez dolduğu an (şu an 100/200
    # gerçek kapanış — yakında) sistem HİÇ karşılaştırma fırsatı olmadan
    # anında %100 adaptive'e geçecekti. multi_timeframe_cascade_ab_test_
    # enabled ile AYNI desen: açıksa statik anahtarın yerine HER karar
    # bağımsız rastgele control (statik ATR)/treatment (adaptive, tablo
    # varsa) kovasına atanır, decisions.experiment_bucket'a etiketlenir —
    # services/ab_testing.py::evaluate_experiment gerçek kapanmış
    # işlemlerle karşılaştırabilsin diye. Varsayılan kapalı — opt-in,
    # tablo dolana kadar zaten hiçbir fark yaratmaz.
    "adaptive_barrier_ab_test_enabled": "false",
    # Faz 268-sonrası — kullanıcı isteği: "farklı bir tipte işlem takip
    # edecek bir modül... AI karar/confidence ile işi olmayan, mevcut
    # sistemden yalıtık." bkz. services/pump_fade_strategy.py — market
    # genelinde son pump_fade_lookback_hours saatte pump_fade_min_gain_pct
    # ve üstü kazanç gösteren USDT perpetual'ları SHORT'lar. Varsayılan
    # KAPALI — kullanıcının kendi sözüyle "test için", opt-in.
    "pump_fade_enabled": "false",
    # Kasanın (starting_capital) yüzde kaçı marjin olarak kullanılacak —
    # kullanıcı isteği: "kasanın %5'i kadar."
    "pump_fade_capital_pct": "0.05",
    # Kullanıcı isteği: "5x pozisyona girecek." Gerçek uygulanan kaldıraç
    # bunun ÜSTÜNE ÇIKMAZ ama simulator/margin.py::max_safe_leverage
    # güvenlik kilidiyle (pump_fade_stop_distance_pct'e göre) daha DÜŞÜK
    # bir değere kırpılabilir — AskUserQuestion ile onaylanan "aynı
    # güvenlik kilidi uygulansın" kararı.
    "pump_fade_leverage": "5",
    # Faz 268-sonrası — kullanıcı isteği: "pump işlemlerinde girmek için
    # matematiksel olarak makul bir seviye." Gerçek piyasa-geneli analiz
    # (527 USDT perpetual, hem 90 günlük hem sembol başına mevcut TÜM
    # geçmiş — 456 gün ortalama, TOPLAM 58.706 gerçek pump olayı, swing-
    # low'dan swing-high'a %10+ hareketler) gösterdi ki eski %100 eşiği
    # gerçekleşen pump'ların ~%99'unu, hatta önceki %50 eşiği bile
    # ~%90'ını hiç yakalamıyordu — medyan pump SADECE %15.1-15.4
    # (iki bağımsız örneklemde tutarlı) civarında tepe yapıp kâr
    # realizasyonuna dönüyor (p25=%12, p75=%22, p90=%35-39). %15 —
    # medyan pump'ın tam yarısının zaten tepe yaptığı, istatistiksel
    # olarak savunulabilir bir eşik. min_gain_pct=1.0, lookback
    # penceresindeki EN DÜŞÜK kapanıştan güncel kapanışa göre ölçülen
    # kazanç oranı (1.0 = %100).
    "pump_fade_min_gain_pct": "0.15",
    # "son iki gün" — 48 saat, 1 saatlik mumlarla taranıyor.
    "pump_fade_lookback_hours": "48",
    # Faz 268-sonrası — kritik tasarım kararı: kullanıcı çıkışı ("%100
    # kâr ettiğinde") onayladı ama KORUYUCU stop-loss mesafesini
    # belirtmedi (sadece "max_safe_leverage ile aynı güvenlik kilidi
    # uygulansın" dedi — bu, BİR stop mesafesi varsayımı gerektiriyor).
    # Kullanıcı bulgusu — gerçek olay: PORTALUSDT/GPSUSDT pump-fade
    # pozisyonları %15 stop'a rağmen sürekli tetiklenme riskiyle karşı
    # karşıyaydı ("pump yapmış bir token inanılmaz volatil olabilir").
    # 198 gerçek pump olayında (fetch_usdt_perpetual_symbols evreni,
    # son ~250 gün) gün-gün SL/TP yarış simülasyonu yapıldı: %15 stopla
    # kazanma oranı %39, ORTALAMA GETİRİ HAM FİYATTA NEGATİF (-%0.15,
    # kaldıraçlı marjin üzerinde -%0.64) — dar stop, gerçek geri dönüş
    # gelmeden normal pump-sonrası volatiliteyle tetikleniyordu. %30
    # stop + %25 hedef kombinasyonu en iyi kaldıraçlı EV'i verdi (kazanma
    # oranı %58.4, ham getiri +%2.13, kaldıraçlı ~+%4.68) — bkz.
    # pump_fade_take_profit_pct'in üstündeki not, TP artık bu ham %'den
    # BAĞIMSIZ ayarlanıyor (leverage'dan türetilmiyor, aksi halde stop
    # genişledikçe leverage düşüp TP sessizce çok uzağa kayardı).
    "pump_fade_stop_distance_pct": "0.30",
    # AYNI 198-olaylık simülasyondan: hedef, kaldıraçtan TÜRETİLMİYOR
    # (eski davranış: take_profit = entry*(1-1/leverage), yani "%100
    # marjin kârı" — stop genişleyip leverage düştükçe bu ham hedefi
    # sessizce %45+'e kaydırıyordu, simülasyonun en iyi bulduğu %25'in
    # çok üstüne). Artık doğrudan bu ham %'ye göre kuruluyor — leverage
    # ne olursa olsun sabit kalır, sadece kaç KATINA denk geldiği
    # (marjin kârı = bu % × gerçek leverage) değişir, o da salt bilgi
    # amaçlı raporlanır.
    "pump_fade_take_profit_pct": "0.25",
    # Faz 268-sonrası — kullanıcı bulgusu: "15 hedge pozisyondan gelen
    # kayıp 400 dolardan fazla, scalp'te 1109 işlem sadece 16 dolar
    # kaybettirmiş — acayip bir dengesizlik." Kök neden: services/
    # pairs_trader.py::LEG_SIZE = 0.2 sabit bir HAM VARLIK BİRİMİYDİ
    # (dolar değil) — 0.2 BTC (~$13.000 notional, 10x kaldıraçla) ile
    # 0.2 ETH (~$380) arasında GERÇEK dolar riski 30 kattan fazla
    # farklıydı, "sabit-küçük bir boyut" niyetinin tam tersi. Artık
    # sabit bir DOLAR tutarı — her bacağın asıl miktarı current_price'a
    # bölünerek hesaplanıyor, tüm varlıklarda GERÇEKTEN aynı boyut.
    "pairs_trading_leg_capital_usd": "100",
}

CANDLE_TIMEFRAMES = ("1m", "5m", "15m", "1h", "4h", "1d")
DISPLAY_CURRENCIES = ("USD", "BTC", "TRY")

# Faz 265 — kritik bulgu: bu değerler Faz 187'de PositionCloser.
# hold_seconds için kurulmuştu ("vade dolunca kapat"), ama Faz 215
# ("bile bile zarar etmek demek bu") bunu tamamen kaldırdı — trade_horizon
# artık pozisyon SÜRESİNİ hiç etkilemiyor, Settings ekranı hâlâ "Scalp
# (~10 dk)" diye vaat ediyordu ama seçimin gerçekte hiçbir etkisi yoktu.
# Kullanıcı isteği: "hem scalp işlem kovalasın hem vade dolunca kapatmasın"
# — bunun gerçek karşılığı SÜRE değil, stop/hedef MESAFESİ: trade_horizon
# artık kısa-vadeli katmanın risk tabanını hangi bar aralığından aldığını
# seçiyor (bkz. services/orchestrator.py::propose, RiskTargetStage hâlâ
# aynı 2.5x/10x oranı uyguluyor, sadece taban ATR'nin kaynağı değişiyor).
# Dar taban (1h) = küçük stop/hedef = saatler içinde sonuçlanma eğilimi
# ("scalp"); geniş taban (1d) = büyük stop/hedef = günler/haftalar
# ("swing") — ama HİÇBİRİ süre yüzünden zorla kapatılmıyor, sadece
# gerçekten stop/hedefe ulaşınca.
TRADE_HORIZON_TO_RISK_TIMEFRAME: dict[str, str] = {
    "short": "1h",
    "medium": "4h",
    "long": "1d",
}


class AppSettingModel(Base):
    __tablename__ = "app_settings"
    key = Column(String(64), primary_key=True)
    # Faz 262: kritik bulgu — VARCHAR(256) idi, symbol_leverage gibi
    # açık-uçlu JSON değerler (watchlist büyüdükçe büyür) bunu aşabiliyordu.
    value = Column(Text, nullable=False)
    updated_by = Column(String(128), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class AppSettingsRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, key: str) -> str:
        row = self.session.query(AppSettingModel).filter_by(key=key).first()
        if row is not None:
            return row.value
        return DEFAULTS.get(key, "")

    def get_all(self) -> dict[str, str]:
        rows = {r.key: r.value for r in self.session.query(AppSettingModel).all()}
        return {**DEFAULTS, **rows}

    def get_updated_by(self, key: str) -> str | None:
        """Faz 268-sonrası: kullanıcı isteği — dashboard'un kill switch'in
        GERÇEKTEN tetiklendiğini (updated_by='kill_switch') manuel Durdur
        düğmesinden ayırt edip bildirim gösterebilmesi için. Satır hiç
        yoksa (hiç değiştirilmemiş varsayılan) None — icat edilmiş bir
        kaynak uydurulmaz."""
        row = self.session.query(AppSettingModel).filter_by(key=key).first()
        return row.updated_by if row is not None else None

    def set(self, key: str, value: str, updated_by: str) -> None:
        row = self.session.query(AppSettingModel).filter_by(key=key).first()
        now = datetime.now(UTC)
        if row is None:
            row = AppSettingModel(key=key, value=value, updated_by=updated_by, updated_at=now)
            self.session.add(row)
        else:
            row.value = value
            row.updated_by = updated_by
            row.updated_at = now
        self.session.commit()

    def reset_to_defaults(self, updated_by: str, keys: list[str] | None = None) -> dict[str, str]:
        """Faz 215: kullanıcı isteği — Settings'e tek tuşla "matematiksel
        olarak mantıklı, komisyona ezilmeyen" varsayılanlara dönüş.
        watchlist/trading_mode/ai_enabled gibi kullanıcı tercihi olan
        (trading ekonomisiyle ilgisiz) ayarları KASITLI OLARAK atlıyor —
        sadece DEFAULTS'ta gerçekten mantıklı gerekçeli değeri olan
        anahtarlar sıfırlanıyor."""
        reset_keys = keys or [
            "max_concurrent_positions", "max_capital_pct", "starting_capital",
            "trade_horizon", "act_threshold", "reduce_threshold",
            "min_profit_target_pct", "candle_timeframe", "candle_lookback",
        ]
        for key in reset_keys:
            if key in DEFAULTS:
                self.set(key, DEFAULTS[key], updated_by=updated_by)
        return {k: DEFAULTS[k] for k in reset_keys if k in DEFAULTS}
