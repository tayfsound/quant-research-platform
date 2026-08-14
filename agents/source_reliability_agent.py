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
from datetime import datetime

from services.agent_memory import AgentMemory


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

    def __init__(self, memory: AgentMemory | None = None):
        self.memory = memory or AgentMemory()

    def annotate(self, opinions: list[dict]) -> list[dict]:
        """Her opinion'a GERÇEK isabet oranından hesaplanan source_
        reliability ve benched durumunu ekler."""
        cutoff = self._legacy_cutoff()
        for op in opinions:
            domain = op.get("domain", "unknown")
            summary = self.memory.get_summary(domain, window=self.WINDOW, min_timestamp=cutoff)
            if summary.total_predictions < self.MIN_SAMPLES:
                reliability = 0.5
                benched = False
            else:
                reliability = summary.recent_accuracy
                benched = reliability < self.BENCH_THRESHOLD
            op["source_reliability"] = reliability
            op["data_freshness_hours"] = 0.0
            op["source_count"] = summary.total_predictions
            op["benched"] = benched
        return opinions

    @staticmethod
    def _legacy_cutoff() -> datetime | None:
        # Faz 268-sonrası — kullanıcı isteği: "başlangıç olarak her ajanın
        # kararda eşit ağırlığı olacak şekilde sistemi başlatalım." Eski,
        # bozuk mekanizmanın ürettiği geçmiş kayıtlar bu düzeltmenin
        # devreye girdiği andan (reliability_legacy_cutoff_at) ÖNCE
        # kalıyorsa hiç sayılmıyor — hiçbir kayıt SİLİNMİYOR (Class 2),
        # sadece yeni hesaptan dışarıda bırakılıyor. DB'ye erişilemezse
        # (ör. bazı izole unit testler) fail-closed: kesim yok, tüm geçmiş
        # sayılır.
        try:
            from database.repositories.app_settings_repository import AppSettingsRepository
            from database.session_factory import SessionFactory

            with SessionFactory.get_session() as session:
                raw = AppSettingsRepository(session).get("reliability_legacy_cutoff_at")
            return datetime.fromisoformat(raw) if raw else None
        except Exception:
            return None

    def is_benched(self, domain: str) -> bool:
        summary = self.memory.get_summary(domain, window=self.WINDOW, min_timestamp=self._legacy_cutoff())
        if summary.total_predictions < self.MIN_SAMPLES:
            return False
        return summary.recent_accuracy < self.BENCH_THRESHOLD

    def get_domain_reliability(self, domain: str) -> float:
        summary = self.memory.get_summary(domain, window=self.WINDOW, min_timestamp=self._legacy_cutoff())
        if summary.total_predictions < self.MIN_SAMPLES:
            return 0.5
        return summary.recent_accuracy
