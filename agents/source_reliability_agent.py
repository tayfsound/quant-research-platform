"""Kaynak güvenilirliği ajanı — diğer ajanların güvenilirliğini gerçek
geçmiş ISABET oranına göre puanlar.

Faz 268-sonrası — kullanıcı bulgusu, iki katmanlı kritik hata: (1) eski
implementasyon "reliability"i son 10 kararın ORTALAMA CONFIDENCE'i olarak
hesaplıyordu — ajanın GERÇEKTEN doğru tahmin edip etmediğine (was_correct,
gerçek kâr/zarar) hiç bakmıyordu; kendinden emin ama sürekli yanlış bir
ajan "güvenilir" sayılabiliyordu. (2) Bu hafıza (self.history/self._benched)
sıradan bir Python dict'te tutuluyordu ve CognitiveOrchestrator her
run_trading_cycle_task çağrısında (120 saniyede bir, services/celery_app.py)
SIFIRDAN yaratıldığı için TAMAMEN siliniyordu — "X reliability stayed below
0.35 for 5+ cycles" ifadesi günler süren bir geçmiş DEĞİL, o anki 120
saniyelik geçişte watchlist'teki ardışık 5 SEMBOL demekti.

Artık services/agent_memory.py::AgentMemory'nin GERÇEK, diske kalıcı
yazılan (was_correct alanlı, süreç/cycle sınırlarında kaybolmayan)
kayıtlarından hesaplanıyor — confidence_calibration.py'nin zaten kullandığı
AYNI veri kaynağı. Tamamen stateless: her annotate() çağrısı diskten taze
okur, hiçbir in-process hafıza tutmaz — "her 2 dakikada bir sıfırlanma"
hata sınıfı yapısal olarak ortadan kalkar."""
from analytics.concept_drift import compute_concept_drift
from services.agent_memory import (
    AgentMemory,
    asset_class_of_symbol,
    get_reliability_legacy_cutoff,
)


class SourceReliabilityAgent:
    BENCH_THRESHOLD = 0.35
    # Faz 370-devam — KRİTİK canlı olay (2026-08-29, kullanıcı teşhisi):
    # tek eşikli bench/unbench "0.34 -> bench, 0.36 -> unbench, 0.34 ->
    # bench..." gibi bir eşik civarında salınıma (ping-pong) açıktı.
    # Histerezis: BENCH_THRESHOLD'un altına düşünce susturuluyor ama
    # geri açılmak için DAHA YÜKSEK bir bar (UNBENCH_THRESHOLD) geçmesi
    # gerekiyor — "kanıtlanana kadar sessiz kal" tek yönlü değil, "gerçekten
    # düzeldiğine dair daha güçlü kanıt gelene kadar sessiz kal" iki yönlü.
    UNBENCH_THRESHOLD = 0.55
    # Yeterli gerçek kanıt (kapanmış, yönlü karar) yoksa fail-closed: nötr
    # (tam ağırlık), benched DEĞİL — "kanıtlanana kadar güven" ilkesi,
    # Adaptive Barrier'ın MIN_TOTAL_SAMPLES'ıyla aynı disiplin.
    MIN_SAMPLES = 10
    # Son N gerçek yönlü karar üzerinden — AgentMemory.get_summary'nin
    # zaten kullandığı pencere (Faz 263: eski başarı yeni çöküşü
    # matematiksel olarak gizlemesin).
    WINDOW = 20
    # Faz 370-devam — KRİTİK canlı olay: TEK BAŞINA WINDOW=20'ye
    # dayanmak kendi kendini besleyen bir kilitlenme döngüsüne açıktı
    # (kullanıcı teşhisi): "son 20'de geçici kötü performans -> ajan
    # tamamen susturuluyor -> ajan sustuğu için sonraki kararlarda etkisi
    # yok -> uzun süre sessiz kalabiliyor." Artık üç pencerenin (20/100/
    # 500) Beta-yumuşatılmış tahminlerinin ağırlıklı ortalaması kullanılıyor
    # — kısa pencere hâlâ EN yüksek ağırlıkta (yakın zamandaki gerçek
    # bozulmaya hâlâ hızlı tepki verir) ama büyük, kanıtlanmış bir geçmişi
    # (500 karar) TEK bir kötü 20'lik seri asla tek başına silemiyor.
    MEDIUM_WINDOW = 100
    LONG_WINDOW = 500
    WINDOW_WEIGHTS = {WINDOW: 0.5, MEDIUM_WINDOW: 0.3, LONG_WINDOW: 0.2}
    # Faz 370-devam — KRİTİK canlı olay: performance_weight=0.0 (tam
    # susturma) kendi kendini besleyen bir kilitlenmeye açıktı — kullanıcı
    # teşhisi: "0, 'ajan kötü' demiyor, 'son 20 kararda kötü performans
    # gördüm, artık dinlemiyorum' diyor." MIN_INFLUENCE, en kötü durumda
    # bile ajanın konuşmaya (küçük ağırlıkla) devam etmesini garantiliyor
    # — reliability istatistiği (op["source_reliability"]) DÜRÜST kalıyor
    # (0.10 gibi düşük bir sayı hâlâ raporlanıyor), sadece OY AĞIRLIĞI
    # (effective_influence) asla tam sıfıra inmiyor. Sıfır SADECE gerçek
    # yapısal arızalarda (agent.analyze() exception fırlatması, contexts
    # dict'inde hiç yoksa) kalmalı — kötü PERFORMANS asla "konuşma hakkı
    # yok" anlamına gelmemeli.
    MIN_INFLUENCE = 0.1
    # Faz 268-sonrası — kritik bulgu, kullanıcı bulgusu: MIN_SAMPLES
    # eşiğini az üstünde (ör. 19-23 örneklem) ham recent_accuracy TAM
    # güvenle kullanılıyordu. Gerçek veriyle doğrulandı: macro ajanının
    # son ~23 kararı %82.6 isabetli görünüyordu (LDOUSDT kararında tek
    # başına %84 nihai güvenle kararı taşımasının nedeni buydu), ama AYNI
    # ajanın büyük örneklemli (600+ işlem, iki ayrı gün) geçmiş performansı
    # sadece ~%37 — son "iyi" seri büyük ihtimalle küçük örneklem
    # varyansı, kalıcı bir iyileşme değil. WeightOptimizer bu AYNI sorunu
    # zaten Bayesian (Beta-prior) yumuşatma ile çözmüştü; aynı disiplin
    # (aynı prior_strength=5) burada da uygulanıyor.
    PRIOR_STRENGTH = 5

    # Faz 269-sonrası — kullanıcı isteği: analytics/concept_drift.py
    # (2x2 ki-kare bağımsızlık testi) şu ana kadar SADECE sistem-geneli
    # (tüm ajanlar/semboller karışık, services/risk_state.py) çalışıyordu
    # — bir ajanın GERÇEKTEN, istatistiksel olarak anlamlı şekilde
    # çökmekte olduğu tespit edilse bile, reliability henüz BENCH_
    # THRESHOLD'un altına düşmemişse hiçbir şey değişmiyordu (3. taraf
    # inceleme bulgusu). concept_drift.MIN_SAMPLE_SIZE (20) her iki
    # pencerede de gerekli — WINDOW ile AYNI büyüklük, tutarlı.
    DRIFT_WINDOW = 20

    def __init__(self, memory: AgentMemory | None = None):
        self.memory = memory or AgentMemory()

    def _smoothed_reliability(self, summary) -> float:
        """Ham isabet oranı yerine Beta-prior ile yumuşatılmış tahmin —
        küçük örneklemi nötr (%50) bir öncüle doğru çeker, örneklem
        büyüdükçe ham orana yaklaşır. services/weight_optimizer.py'nin
        smoothed_accuracy'siyle AYNI formül — tek gerçek kaynak yerine iki
        ayrı ama tutarsız hesap olmasın diye matematiksel olarak özdeş
        tutuldu.

        Faz 370-devam — KRİTİK bulgu (multi-window blend'i yazarken
        ampirik olarak ortaya çıktı): summary.overall_accuracy KULLANILIYOR,
        summary.recent_accuracy DEĞİL. AgentMemory.get_summary()'nin
        recent_accuracy alanı `records[-20:]` ile SABİT kodlanmış — get_
        summary'ye HANGİ window verilirse verilsin (100, 500...) her zaman
        SON 20'nin isabetini döndürüyor (window=20 için overall_accuracy
        ile tesadüfen özdeş, o yüzden eski tek-pencereli kod bunu hiç
        fark etmemişti). overall_accuracy ise GERÇEKTEN window-kapsamlı
        (summary.total_predictions'ın kendi hesaplandığı AYNI kayıt
        kümesinden) — çoklu pencere karışımının anlamlı olması için doğru
        alan bu."""
        correct = round(summary.overall_accuracy * summary.total_predictions)
        return (correct + self.PRIOR_STRENGTH) / (summary.total_predictions + self.PRIOR_STRENGTH * 2)

    def _summary_for(self, domain: str, symbol: str | None, cutoff, window: int | None = None, regime: str | None = None):
        """Faz 268-sonrası — kullanıcı bulgusu, gerçek veriyle doğrulandı:
        ajan performansı varlık sınıfına göre büyük ölçüde farklılaşıyor
        (macro kripto'da %30.5, kripto-dışında %55.4; technical TAM
        TERSİ). Global (tüm varlık sınıflarını karıştıran) tek bir
        özet, her iki bağlamda da yanlış bir sinyal veriyordu.

        Faz 370-devam — kullanıcı isteği: "technical overall kötü olması,
        technical bullish_low'da da kötü demek değil — global bench
        yerine agent×regime reliability." `regime` verilirse (deliberate()
        çağıranın zaten hesapladığı trend_volatility string'i, AynI
        format services/kelly_sizing.py'nin regime-koşullu Kelly'sinde de
        kullanılıyor) ÖNCE o rejime özel özete bakılır (yeterli örneklem
        varsa) — "technical şu an genel olarak kötü ama BU rejimde
        tarihsel olarak güçlü" ayrımını yakalamak için. Yetersizse sembol
        verilirse varlık sınıfına, o da yetersizse (ya da hiçbiri
        verilmemişse) GLOBAL özete düşülür — confidence_calibration.py::
        _calibration_curve_for ile AYNI kademeli fail-closed desen."""
        window = window or self.WINDOW
        if regime:
            regime_summary = self.memory.get_summary(domain, window=window, min_timestamp=cutoff, regime=regime)
            if regime_summary.total_predictions >= self.MIN_SAMPLES:
                return regime_summary
        if symbol:
            asset_class = asset_class_of_symbol(symbol)
            class_summary = self.memory.get_summary(
                domain, window=window, min_timestamp=cutoff, asset_class=asset_class
            )
            if class_summary.total_predictions >= self.MIN_SAMPLES:
                return class_summary
        return self.memory.get_summary(domain, window=window, min_timestamp=cutoff)

    def _blended_reliability(self, domain: str, symbol: str | None, cutoff, regime: str | None = None) -> tuple[float | None, int]:
        """Faz 370-devam — KRİTİK canlı olay: kullanıcı teşhisi, bkz.
        WINDOW_WEIGHTS üstündeki sınıf yorumu. Üç pencerenin (20/100/500)
        Beta-yumuşatılmış (_smoothed_reliability) tahminlerinin ağırlıklı
        ortalamasını döner — TEK bir 20'lik kötü seri artık tek başına
        kararı belirlemiyor, ama yakın zaman hâlâ en yüksek ağırlıkta
        (gerçek, kalıcı bir bozulmaya hâlâ makul hızda tepki veriyor).
        Her pencere kendi MIN_SAMPLES eşiğini bağımsız uygular (fail-
        closed) — yetersiz pencereler ortalamadan TAMAMEN çıkarılır,
        icat edilmiş bir sayı asla katkı vermez; ağırlıklar kalan
        pencereler arasında yeniden normalize edilir. HİÇBİR pencere
        yeterli değilse (None, total_predictions) döner — çağıran bunu
        "kanıtlanana kadar nötr" olarak ele almalı, mevcut MIN_SAMPLES
        disiplini korunuyor.

        Dönen tuple'ın ikinci elemanı EN KISA (WINDOW=20) pencerenin
        total_predictions'ı — mevcut "yeterli kanıt var mı" UI/log
        alanlarıyla (op["source_count"]) geriye dönük uyumlu kalsın diye."""
        weighted_sum = 0.0
        weight_total = 0.0
        short_window_count = 0
        for window, weight in self.WINDOW_WEIGHTS.items():
            summary = self._summary_for(domain, symbol, cutoff, window=window, regime=regime)
            if window == self.WINDOW:
                short_window_count = summary.total_predictions
            if summary.total_predictions < self.MIN_SAMPLES:
                continue
            weighted_sum += self._smoothed_reliability(summary) * weight
            weight_total += weight
        if weight_total == 0.0:
            return None, short_window_count
        return weighted_sum / weight_total, short_window_count

    def _records_for_drift(self, domain: str, symbol: str | None, cutoff):
        """_summary_for ile AYNI sembol/varlık-sınıfı öncelik sırası
        (yeterli örneklemli sembole özel geçmiş varsa o, yoksa global) —
        ama özetlenmemiş ham kayıtlar (Concept Drift'in baseline/recent
        iki AYRI pencereye ihtiyacı var, tek bir özet yetmiyor)."""
        if symbol:
            asset_class = asset_class_of_symbol(symbol)
            class_records = self.memory.get_filtered_records(
                domain, min_timestamp=cutoff, asset_class=asset_class
            )
            if len(class_records) >= self.DRIFT_WINDOW * 2:
                return class_records
        return self.memory.get_filtered_records(domain, min_timestamp=cutoff)

    def _domain_drift_detected(self, domain: str, symbol: str | None, cutoff) -> bool:
        """Son DRIFT_WINDOW karar (recent) ile ondan hemen önceki AYNI
        büyüklükteki pencere (baseline) arasında istatistiksel olarak
        anlamlı VE GERİLEYEN (iyileşme değil) bir doğruluk düşüşü varsa
        True — reliability eşiğinin üstünde kalsa bile. <2*DRIFT_WINDOW
        gerçek yönlü kayıt varsa (fail-closed) her zaman False."""
        records = self._records_for_drift(domain, symbol, cutoff)
        if len(records) < self.DRIFT_WINDOW * 2:
            return False
        recent = records[-self.DRIFT_WINDOW:]
        baseline = records[-self.DRIFT_WINDOW * 2:-self.DRIFT_WINDOW]
        drift = compute_concept_drift(
            [r.was_correct for r in baseline],
            [r.was_correct for r in recent],
        )
        if drift is None:
            return False
        return drift["drift_detected"] and drift["recent_win_rate"] < drift["baseline_win_rate"]

    def _bench_state_key(self, domain: str) -> str:
        """Faz 370-devam — kritik izolasyon detayı: app_settings TÜM
        namespace'ler arasında PAYLAŞIMLI, yeni bir tablo/migration icat
        etmeden histerezis biti için en doğal yer — ama bu yüzden anahtar
        self.memory.namespace'i de içermeli. AgentMemory zaten HER pytest
        sürecinin/test'in kendi benzersiz namespace'ini kullanıyor (bkz.
        conftest.py + AgentMemory docstring'i) — namespace'i anahtara
        katmak, testler arası sızıntıyı (app_settings, quantdb_test
        temizliğinde BİLEREK korunan 5 tablodan biri, purge edilmiyor)
        YAPISAL olarak imkansız kılıyor, ayrı bir test-cleanup fixture'ına
        gerek kalmadan. Canlı/üretim namespace'i ('') her zaman AYNI
        kalıcı anahtarı kullanmaya devam ediyor — davranış DEĞİŞMEDİ.

        app_settings.key VARCHAR(64) — gerçek namespace'ler (özellikle
        test tmp_path'leri, tam bir dosya sistemi yolu) bu sınırı kolayca
        aşıyor. Namespace'in kendisi yerine kısa bir hash'i kullanılıyor
        — çakışma pratikte imkansız (12 hex karakter = 48 bit), okunabilir
        olması gerekmiyor (sadece izolasyon için)."""
        import hashlib

        namespace_hash = hashlib.md5(self.memory.namespace.encode()).hexdigest()[:12]
        return f"agent_bench_state__{namespace_hash}__{domain}"

    def _get_persisted_bench_state(self, domain: str) -> bool:
        """Histerezis, domain-seviyesinde (sembol/rejim bazlı DEĞİL —
        sadeliği ve öngörülebilirliği korumak için kasıtlı seçim) tek bir
        kalıcı bit gerektiriyor: "bu domain ŞU AN bench durumunda mı."
        Satır hiç yoksa (ilk çalıştırma) fail-closed: False (bench değil)
        — mevcut davranışla (stateless, hep yeniden hesaplanan) geriye
        dönük uyumlu ilk an."""
        from database.repositories.app_settings_repository import AppSettingsRepository
        from database.session_factory import SessionFactory

        with SessionFactory.get_session() as session:
            return AppSettingsRepository(session).get(self._bench_state_key(domain)) == "true"

    def _persist_bench_state_if_changed(self, domain: str, previous: bool, new: bool) -> None:
        """SADECE durum GERÇEKTEN değiştiğinde yazar — annotate() cycle
        başına onlarca sembol için çağrıldığından (81 sembol × 12 domain),
        her çağrıda yazmak gereksiz DB yükü olurdu; geçiş anları (bench
        oldu/bench'ten çıktı) zaten nadir."""
        if previous == new:
            return
        from database.repositories.app_settings_repository import AppSettingsRepository
        from database.session_factory import SessionFactory

        with SessionFactory.get_session() as session:
            AppSettingsRepository(session).set(
                self._bench_state_key(domain), "true" if new else "false",
                updated_by="source_reliability_agent",
            )

    def annotate(self, opinions: list[dict], symbol: str | None = None, regime: str | None = None) -> list[dict]:
        """Her opinion'a GERÇEK isabet oranından hesaplanan source_
        reliability ve benched durumunu ekler. symbol verilirse (bu
        council cycle'ının hangi enstrüman için çalıştığı) önce o
        enstrümanın varlık sınıfına özel geçmiş kullanılır.

        Faz 367-devam — kullanıcı isteği: "ajanları kendi başlarına
        değerlendirmeye devam ettiğimiz sürece çözemeyiz — başarı
        kriterleri diğer ajanlarla ilişkiler silsilesi." Gerçek bulgu:
        sentiment solo %5 ama pattern+sentiment %100 (bkz. contracts/
        agent.py'nin sentiment notu); technical'ın SHORT'u solo çok kötü
        görünse de (bu belirli dönemde PİYASA-GENELİ bir rejim etkisi —
        tüm ajanlarda aynı desen doğrulandı) bu SOLO ölçüm asla o anki
        gerçek KOMBİNASYON bağlamını görmüyordu. Artık her opinion'ın
        `direction`ı da (varsa) veriliyorsa: bu domain'le AYNI yönde oy
        veren diğer domain'lerle birlikte, en son haftalık raporun
        GÜVENİLİR (FDR'ı geçmiş + düşük örtüşmeli — analytics/agent_
        combination_reliability_gate.py::trustworthy_known_pairs ile AYNI
        filtre) VE eşik-üstü (agent_combination_gate_min_win_rate) bir
        grubun alt kümesiyse, solo-bench kararı GEÇERSİZ kılınır — o anki
        GERÇEK şirket güçlüyse, geçmiş solo zayıflık tek başına artık
        susturmuyor. Rapor yoksa/eşleşme yoksa (fail-closed) davranış hiç
        değişmez."""
        cutoff = get_reliability_legacy_cutoff()
        trustworthy_groups = self._load_trustworthy_groups()
        direction_by_domain = {
            op.get("domain"): op.get("direction")
            for op in opinions
            if op.get("direction") in ("LONG", "SHORT")
        }
        for op in opinions:
            domain = op.get("domain", "unknown")
            blended, short_window_count = self._blended_reliability(domain, symbol, cutoff, regime=regime)
            if blended is None:
                reliability = 0.5
                benched = False
            else:
                reliability = round(blended, 3)
                # Faz 370-devam — histerezis (kullanıcı isteği): geri
                # açılmak için DAHA YÜKSEK bir bar (UNBENCH_THRESHOLD)
                # gerekiyor — eşik civarında salınımı (ping-pong) önler.
                # Zaten bench durumundaysa BENCH_THRESHOLD'a geri düşmek
                # yetmiyor, UNBENCH_THRESHOLD'u GEÇMESİ gerekiyor; henüz
                # bench değilse normal (tek, düşük) eşik geçerli.
                was_benched = self._get_persisted_bench_state(domain)
                if was_benched:
                    benched = reliability < self.UNBENCH_THRESHOLD
                else:
                    benched = reliability < self.BENCH_THRESHOLD
                self._persist_bench_state_if_changed(domain, was_benched, benched)
            if not benched and self._domain_drift_detected(domain, symbol, cutoff):
                benched = True
            combination_override = False
            if benched and domain in direction_by_domain:
                agreeing_now = {
                    d for d, dirn in direction_by_domain.items()
                    if dirn == direction_by_domain[domain]
                }
                if self._matches_a_trustworthy_group(agreeing_now, trustworthy_groups):
                    benched = False
                    combination_override = True
            op["source_reliability"] = reliability
            op["data_freshness_hours"] = 0.0
            op["source_count"] = short_window_count
            op["benched"] = benched
            op["combination_override_applied"] = combination_override
        return opinions

    @staticmethod
    def _load_trustworthy_groups() -> list[dict]:
        try:
            from database.repositories.agent_combination_reliability_report_repository import (
                AgentCombinationReliabilityReportRepository,
            )
            from database.repositories.app_settings_repository import AppSettingsRepository
            from database.session_factory import SessionFactory

            with SessionFactory.get_session() as session:
                report = AgentCombinationReliabilityReportRepository(session).get_latest()
                min_win_rate_raw = AppSettingsRepository(session).get("agent_combination_gate_min_win_rate")
        except Exception:
            return []
        if not report or not report.get("result"):
            return []

        from analytics.agent_combination_reliability_gate import DEFAULT_MIN_WIN_RATE, trustworthy_known_pairs

        threshold = float(min_win_rate_raw) if min_win_rate_raw else DEFAULT_MIN_WIN_RATE
        trustworthy = trustworthy_known_pairs(report["result"].get("pairs") or [])
        return [g for g in trustworthy if g.get("win_rate", 0.0) >= threshold]

    @staticmethod
    def _matches_a_trustworthy_group(agreeing_now: set, trustworthy_groups: list[dict]) -> bool:
        return any(set(g.get("domains", [])) <= agreeing_now for g in trustworthy_groups)

    def is_benched(self, domain: str, symbol: str | None = None, regime: str | None = None) -> bool:
        """Faz 370-devam — annotate()'in çoklu-pencere + histerezis
        mantığıyla TUTARLI, ama SADECE OKUYAN (annotate()'in aksine
        histerezis durumunu YAZMAZ — bu, dashboard/tanı amaçlı bağımsız
        çağrıların canlı karar döngüsünün durumunu yanlışlıkla
        değiştirmemesi için kasıtlı)."""
        cutoff = get_reliability_legacy_cutoff()
        blended, _ = self._blended_reliability(domain, symbol, cutoff, regime=regime)
        if blended is not None:
            threshold = self.UNBENCH_THRESHOLD if self._get_persisted_bench_state(domain) else self.BENCH_THRESHOLD
            if blended < threshold:
                return True
        return self._domain_drift_detected(domain, symbol, cutoff)

    def get_domain_reliability(self, domain: str, symbol: str | None = None, regime: str | None = None) -> float:
        blended, _ = self._blended_reliability(domain, symbol, get_reliability_legacy_cutoff(), regime=regime)
        return round(blended, 3) if blended is not None else 0.5
