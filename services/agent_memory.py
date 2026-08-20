"""Agent Memory — persistent storage backed by Postgres/TimescaleDB."""

import os

from sqlalchemy import text

from contracts.agent_performance import (
    AgentPerformanceRecord,
    AgentPerformanceSummary,
)
from database.session_factory import SessionFactory

# Faz 319 — kullanıcı isteği: agent_memory_history/agent_memory.json (tek
# dosya, fcntl kilitli, 60.519 kayıt) yerine gerçek bir Postgres tablosu
# (decisions/weight_approvals ile AYNI TimescaleDB hypertable deseni, bkz.
# faz319 migration). Gerçek geçmiş veri scripts/migrate_agent_memory_to_
# postgres.py ile bir kerelik taşındı.
#
# `_DEFAULT_NAMESPACE`/`storage_path` artık bir dosya yolu DEĞİL — yeni
# `namespace` sütununun değeri. Bu KASITLI: testler (38 çağrı noktası)
# bugüne kadar AgentMemory(storage_path=str(tmp_path/...)) ile GERÇEK bir
# izolasyon alıyordu (her test kendi boş JSON dizinini kullanır, paylaşımlı
# canlı dosyaya ya da birbirine asla karışmaz). Bu davranışı Postgres'te
# birebir korumak için storage_path string'i artık doğrudan namespace
# sütununa yazılıyor/filtreleniyor — hiçbir test dosyası değişmedi.
# Gerçek/canlı kayıtlar (AgentMemory() varsayılanı) namespace='' kullanır.
# conftest.py de değişmedi: AGENT_MEMORY_STORAGE_PATH ortam değişkeni artık
# bir dizin yolu değil ama string olarak AYNI izolasyon rolünü (testlerin
# paylaşımlı canlı namespace'ten ayrılması) oynamaya devam ediyor.
_DEFAULT_NAMESPACE = os.environ.get("AGENT_MEMORY_STORAGE_PATH", "")

# Faz 247 — services/confidence_calibration.py'den taşındı (Faz 268-sonrası):
# kullanıcı bulgusu, gerçek veriyle doğrulandı — macro ajanı kripto'da %30.5,
# kripto-dışında (hisse/endeks/emtia) %55.4 isabetli; technical ise TAM
# TERSİ (kripto %61.8, kripto-dışı %35.0). SourceReliabilityAgent'ın
# benching/güvenilirlik hesabı bu ikisini TEK bir global ortalamada
# karıştırıyordu — buraya taşınmasının nedeni: hem confidence_calibration.py
# hem source_reliability_agent.py (agent_memory üzerinden) AYNI sınıflandırmayı
# kullanmalı, iki ayrı/uyuşmaz tanım olmasın.
_ASSET_CLASS_SYMBOLS: dict[str, tuple[str, ...]] = {
    "gold_backed": ("PAXGUSDT", "XAUTUSDT"),
    "precious_metal_future": ("GC=F", "SI=F"),
    "equity_index": ("^IXIC", "^GSPC"),
    "equity": ("AAPL", "NVDA", "MSFT"),
}
_CRYPTO_QUOTE_SUFFIXES = ("USDT", "BUSD", "USDC", "FDUSD")


def asset_class_of_symbol(symbol: str) -> str:
    s = (symbol or "").upper()
    for asset_class, symbols in _ASSET_CLASS_SYMBOLS.items():
        if s in symbols:
            return asset_class
    if s.endswith(_CRYPTO_QUOTE_SUFFIXES):
        return "crypto"
    return "other"


def _effective_decision_timestamp(record: AgentPerformanceRecord):
    """decision_opened_at (DB'den, tz-aware/UTC) ile timestamp (datetime.now(),
    tz-naive) AYNI kayıt kümesinde karışabiliyor — Python ikisini doğrudan
    karşılaştıramaz (TypeError). Karşılaştırmayı hep tz-naive'e indirger;
    birkaç saatlik yerel/UTC farkı bu "en yeni N kayıt" penceresinin amacı
    için (gün mertebesinde doğru sıralama) önemsiz."""
    ts = record.decision_opened_at or record.timestamp
    return ts.replace(tzinfo=None) if ts.tzinfo is not None else ts


def get_reliability_legacy_cutoff():
    """Faz 268-sonrası — kullanıcı isteği: "başlangıç olarak her ajanın
    kararda eşit ağırlığı olsun." reliability_legacy_cutoff_at (kill_
    switch_legacy_cutoff_at ile AYNI Class 2 deseni) set edildiğinde, bu
    tarihten ÖNCEKİ AgentPerformanceRecord'lar hiçbir gerçek isabet/
    ağırlık hesabına girmiyor — hiçbir kayıt SİLİNMİYOR, sadece dışarıda
    bırakılıyor. TEK kaynak: hem agents/source_reliability_agent.py
    (per-cycle benching) hem services/weight_optimizer.py (kalıcı global
    ağırlık önerileri) BURAYI çağırmalı — aksi halde ikisi arasında
    tutarsız bir "eşit başlangıç" ortaya çıkar (gerçek olay: ilki
    sıfırlandı, ikincisi hâlâ eski/bozuk dönemin verisini kullanmaya
    devam etti). DB'ye erişilemezse (ör. izole unit testler) fail-closed:
    kesim yok, tüm geçmiş sayılır."""
    try:
        from database.repositories.app_settings_repository import AppSettingsRepository

        with SessionFactory.get_session() as session:
            raw = AppSettingsRepository(session).get("reliability_legacy_cutoff_at")
        from datetime import datetime
        return datetime.fromisoformat(raw) if raw else None
    except Exception:
        return None


# AgentPerformanceRecord'un TÜM alanları (id dahil) — INSERT/SELECT'in
# sütun listesini modelle senkron tutmak için tek yerde.
_RECORD_COLUMNS = [
    "id", "agent_domain", "timestamp", "decision_opened_at", "direction",
    "confidence", "was_correct", "source", "decision_score", "r_multiple",
    "pnl", "failure_type", "symbol", "market_regime", "timeframe",
    "volatility", "session", "spread", "funding", "leverage",
    "holding_time_minutes", "news_type", "reasoning", "error_analysis",
]


class AgentMemory:

    def __init__(self, storage_path: str = _DEFAULT_NAMESPACE):
        self.namespace = storage_path

    def record(self, record: AgentPerformanceRecord):
        payload = record.model_dump(mode="python")
        payload["namespace"] = self.namespace
        columns = ["namespace", *_RECORD_COLUMNS]
        placeholders = ", ".join(f":{c}" for c in columns)
        with SessionFactory.get_session() as session:
            session.execute(
                text(
                    f"INSERT INTO agent_performance_records ({', '.join(columns)}) "
                    f"VALUES ({placeholders})"
                ),
                payload,
            )

    def domains(self) -> list[str]:
        with SessionFactory.get_session() as session:
            rows = session.execute(
                text(
                    "SELECT DISTINCT agent_domain FROM agent_performance_records "
                    "WHERE namespace = :namespace"
                ),
                {"namespace": self.namespace},
            ).fetchall()
        return [r[0] for r in rows]

    def total_record_count(self) -> int:
        """Bu namespace'teki TÜM kayıtların (yön/domain filtresiz) sayısı —
        get_filtered_records/get_summary'nin SADECE LONG/SHORT yönlü
        kayıtları saydığı filtrelemenin dışında, "hiç yeni satır eklendi
        mi" gibi ham bir sayaç gereken testler için."""
        with SessionFactory.get_session() as session:
            count = session.execute(
                text(
                    "SELECT COUNT(*) FROM agent_performance_records WHERE namespace = :namespace"
                ),
                {"namespace": self.namespace},
            ).scalar()
        return int(count or 0)

    def _query_domain_records(self, domain: str) -> list[AgentPerformanceRecord]:
        with SessionFactory.get_session() as session:
            rows = session.execute(
                text(
                    f"SELECT {', '.join(_RECORD_COLUMNS)} FROM agent_performance_records "
                    "WHERE namespace = :namespace AND agent_domain = :domain"
                ),
                {"namespace": self.namespace, "domain": domain},
            ).mappings().all()
        return [AgentPerformanceRecord.model_validate(dict(r)) for r in rows]

    def get_filtered_records(
        self,
        domain: str,
        regime: str | None = None,
        min_timestamp=None,
        asset_class: str | None = None,
    ) -> list[AgentPerformanceRecord]:
        """get_summary()'nin filtreleme/sıralama mantığıyla AYNI (SADECE
        gerçek yönlü kayıtlar, kararın VERİLDİĞİ ana göre sıralı) ama
        özetlenmemiş, ham kayıt listesi döner — Concept Drift'in (baseline
        vs recent iki AYRI pencere) ihtiyaç duyduğu ham win/loss dizisini
        oluşturmak için (bkz. agents/source_reliability_agent.py::
        _domain_drift_detected). get_summary() kasıtlı olarak DEĞİŞTİRİLMEDİ
        — mevcut, çok test edilmiş davranışı bozma riski sıfır."""
        records = [
            r for r in self._query_domain_records(domain)
            if (r.direction or "").upper() in ("LONG", "SHORT")
        ]
        records = sorted(records, key=_effective_decision_timestamp)
        if regime is not None:
            records = [r for r in records if (r.market_regime or "unknown") == regime]
        if asset_class is not None:
            records = [r for r in records if asset_class_of_symbol(r.symbol) == asset_class]
        if min_timestamp is not None:
            cutoff = min_timestamp.replace(tzinfo=None) if min_timestamp.tzinfo is not None else min_timestamp
            records = [r for r in records if _effective_decision_timestamp(r) >= cutoff]
        return records

    def get_summary(
        self,
        domain: str,
        window: int | None = None,
        regime: str | None = None,
        min_timestamp=None,
        asset_class: str | None = None,
    ) -> AgentPerformanceSummary:
        # Faz 253: kritik bulgu — canlıda doğrulandı. Faz 245, WAIT diyen
        # bir ajanın kaydedilmesini (record() çağrısını) durdurmuştu ama
        # get_summary() hâlâ dosyada zaten duran ESKİ WAIT kayıtlarını da
        # doğruluk hesabına katıyordu. time/epistemology ajanlarının
        # TAMAMI (3517/3516 kayıt) WAIT — bu ajanlar hiç yönlü tahmin
        # yapmadı, yine de WeightOptimizer onları gerçek beceriymiş gibi
        # "%82.5 doğru" görüp bir onay üretti, kullanıcı bunu fark etmeden
        # onayladı. Artık burada da SADECE gerçekten yönlü (LONG/SHORT)
        # kayıtlar sayılıyor — WAIT bir tahmin değil, doğru/yanlış
        # ölçülemez.
        records = [
            r for r in self._query_domain_records(domain)
            if (r.direction or "").upper() in ("LONG", "SHORT")
        ]

        # Faz 268-sonrası — gerçek bulgu: kayıtlar record() çağrıldığı sırada
        # (pozisyon KAPANDIĞINDA) dosyaya ekleniyor — insertion sırası kapanış
        # sırasıdır, kararın VERİLDİĞİ sıra değil. Eski (haftalar önce açılmış)
        # bir pozisyon grubu aynı gün toplu kapanınca, aşağıdaki window/
        # min_timestamp/"son 20" mantığı o günün gerçek yeni kararları yerine
        # o eski/bozuk dönemde verilmiş kararları görüyordu (bkz. contracts/
        # agent_performance.py::decision_opened_at yorumu). Artık "en yeni"
        # her zaman kararın VERİLDİĞİ ana göre — decision_opened_at yoksa
        # (bu alan eklenmeden önceki eski kayıtlar) timestamp'e düşülüyor.
        records = sorted(records, key=_effective_decision_timestamp)

        # Faz 268b — Regime-Aware Learning: regime verilirse, SADECE o
        # piyasa rejiminde alınmış gerçek kararlar sayılır. window (aşağıda)
        # bu filtreden SONRA uygulanıyor — "bu rejimin en yeni N kaydı",
        # "tüm rejimlerin en yeni N'i sonra bu rejime göre filtrelenmiş
        # kalanı" değil.
        if regime is not None:
            records = [r for r in records if (r.market_regime or "unknown") == regime]

        # Faz 268-sonrası — kullanıcı bulgusu: ajan performansı varlık
        # sınıfına göre büyük ölçüde farklılaşıyor (gerçek veriyle
        # doğrulandı: macro kripto'da %30.5, kripto-dışında %55.4;
        # technical TAM TERSİ, kripto'da %61.8, kripto-dışında %35.0).
        # Global (tüm varlık sınıflarını karıştıran) tek bir ortalama, her
        # iki bağlamda da yanlış bir sinyal veriyordu. asset_class
        # verilirse SADECE o sınıftaki gerçek kararlar sayılır.
        if asset_class is not None:
            records = [r for r in records if asset_class_of_symbol(r.symbol) == asset_class]

        # Faz 268-sonrası — kullanıcı isteği: SourceReliabilityAgent'ın
        # gerçek isabet oranına geçmesiyle birlikte eklendi (bkz. agents/
        # source_reliability_agent.py) — "reliability_legacy_cutoff_at"
        # ayarı kill_switch_legacy_cutoff_at ile AYNI Class 2 deseni: bu
        # tarihten ÖNCEKİ kayıtlar sayılmıyor, eski/bozuk mekanizmanın
        # dönemi yeni hesaba hiç karışmıyor (satırlar silinmiyor, sadece
        # dışarıda bırakılıyor).
        if min_timestamp is not None:
            cutoff = min_timestamp.replace(tzinfo=None) if min_timestamp.tzinfo is not None else min_timestamp
            records = [r for r in records if _effective_decision_timestamp(r) >= cutoff]

        # Faz 263 — kritik bulgu: WeightOptimizer.propose_weights() bu
        # metodu window'suz çağırıyordu, yani ağırlıklar HER ZAMAN tüm
        # geçmişin ortalamasına göre belirleniyordu. Gerçek veriyle
        # doğrulandı: technical_agent'ın tüm-zamanlar doğruluğu %76.7 ama
        # SON 20 tahmininin sadece %15'i doğru — ajan gerçekte çökmüş
        # durumdayken hâlâ yüksek ağırlıkla oy kullanıyordu, çünkü eski
        # (artık geçerli olmayan) başarısı yeni çöküşü matematiksel olarak
        # gizliyordu. window verilirse SADECE o kadar en yeni yönlü kayıt
        # kullanılır — WeightOptimizer artık kendi evaluation_window
        # parametresini (adının vaat ettiği gibi) gerçekten uyguluyor.
        if window is not None and window > 0:
            records = records[-window:]

        if not records:
            return AgentPerformanceSummary(
                agent_domain=domain
            )

        total = len(records)

        correct = sum(
            1
            for r in records
            if r.was_correct
        )

        overall = correct / total

        by_regime: dict[str, list[bool]] = {}

        for r in records:

            regime = (
                r.market_regime
                if r.market_regime
                else "unknown"
            )

            by_regime.setdefault(
                regime,
                [],
            ).append(r.was_correct)

        regime_accuracy = {
            regime: sum(values) / len(values)
            for regime, values in by_regime.items()
        }

        recent = records[-20:]

        recent_accuracy = (
            sum(
                1
                for r in recent
                if r.was_correct
            )
            / len(recent)
        ) if recent else 0.0

        return AgentPerformanceSummary(
            agent_domain=domain,
            overall_accuracy=round(overall, 3),
            total_predictions=total,
            by_regime=regime_accuracy,
            recent_accuracy=round(recent_accuracy, 3),
        )


    def get_contextual_confidence(
        self,
        domain: str,
        market_regime: str = "",
    ) -> float:

        summary = self.get_summary(domain)

        if summary.total_predictions < 5:
            return 0.5

        regime = summary.by_regime.get(
            market_regime,
            summary.overall_accuracy,
        )

        return round(
            regime * 0.5
            + summary.overall_accuracy * 0.3
            + summary.recent_accuracy * 0.2,
            3,
        )
