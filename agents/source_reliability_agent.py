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
    # Yeterli gerçek kanıt (kapanmış, yönlü karar) yoksa fail-closed: nötr
    # (tam ağırlık), benched DEĞİL — "kanıtlanana kadar güven" ilkesi,
    # Adaptive Barrier'ın MIN_TOTAL_SAMPLES'ıyla aynı disiplin.
    MIN_SAMPLES = 10
    # Son N gerçek yönlü karar üzerinden — AgentMemory.get_summary'nin
    # zaten kullandığı pencere (Faz 263: eski başarı yeni çöküşü
    # matematiksel olarak gizlemesin).
    WINDOW = 20
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
        """Ham recent_accuracy yerine Beta-prior ile yumuşatılmış tahmin
        — küçük örneklemi nötr (%50) bir öncüle doğru çeker, örneklem
        büyüdükçe ham orana yaklaşır. services/weight_optimizer.py'nin
        smoothed_accuracy'siyle AYNI formül — tek gerçek kaynak yerine iki
        ayrı ama tutarsız hesap olmasın diye matematiksel olarak özdeş
        tutuldu."""
        correct = round(summary.recent_accuracy * summary.total_predictions)
        return (correct + self.PRIOR_STRENGTH) / (summary.total_predictions + self.PRIOR_STRENGTH * 2)

    def _summary_for(self, domain: str, symbol: str | None, cutoff):
        """Faz 268-sonrası — kullanıcı bulgusu, gerçek veriyle doğrulandı:
        ajan performansı varlık sınıfına göre büyük ölçüde farklılaşıyor
        (macro kripto'da %30.5, kripto-dışında %55.4; technical TAM
        TERSİ). Global (tüm varlık sınıflarını karıştıran) tek bir
        özet, her iki bağlamda da yanlış bir sinyal veriyordu.

        symbol verilirse önce O SEMBOLÜN varlık sınıfına özel özete
        bakılır (yeterli örneklem varsa); yetersizse (ya da symbol hiç
        verilmezse) confidence_calibration.py::_calibration_curve_for
        ile AYNI fail-closed desenle GLOBAL (tüm sınıflar) özete
        düşülür — tamamen nötre düşmeden önce elimizdeki en iyi kanıtı
        kullanmaya çalışıyoruz."""
        if symbol:
            asset_class = asset_class_of_symbol(symbol)
            class_summary = self.memory.get_summary(
                domain, window=self.WINDOW, min_timestamp=cutoff, asset_class=asset_class
            )
            if class_summary.total_predictions >= self.MIN_SAMPLES:
                return class_summary
        return self.memory.get_summary(domain, window=self.WINDOW, min_timestamp=cutoff)

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

    def annotate(self, opinions: list[dict], symbol: str | None = None) -> list[dict]:
        """Her opinion'a GERÇEK isabet oranından hesaplanan source_
        reliability ve benched durumunu ekler. symbol verilirse (bu
        council cycle'ının hangi enstrüman için çalıştığı) önce o
        enstrümanın varlık sınıfına özel geçmiş kullanılır."""
        cutoff = get_reliability_legacy_cutoff()
        for op in opinions:
            domain = op.get("domain", "unknown")
            summary = self._summary_for(domain, symbol, cutoff)
            if summary.total_predictions < self.MIN_SAMPLES:
                reliability = 0.5
                benched = False
            else:
                reliability = round(self._smoothed_reliability(summary), 3)
                benched = reliability < self.BENCH_THRESHOLD
            if not benched and self._domain_drift_detected(domain, symbol, cutoff):
                benched = True
            op["source_reliability"] = reliability
            op["data_freshness_hours"] = 0.0
            op["source_count"] = summary.total_predictions
            op["benched"] = benched
        return opinions

    def is_benched(self, domain: str, symbol: str | None = None) -> bool:
        cutoff = get_reliability_legacy_cutoff()
        summary = self._summary_for(domain, symbol, cutoff)
        if summary.total_predictions >= self.MIN_SAMPLES and self._smoothed_reliability(summary) < self.BENCH_THRESHOLD:
            return True
        return self._domain_drift_detected(domain, symbol, cutoff)

    def get_domain_reliability(self, domain: str, symbol: str | None = None) -> float:
        summary = self._summary_for(domain, symbol, get_reliability_legacy_cutoff())
        if summary.total_predictions < self.MIN_SAMPLES:
            return 0.5
        return round(self._smoothed_reliability(summary), 3)
