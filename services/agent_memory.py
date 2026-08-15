"""Agent Memory — persistent storage backed by JSON."""

import fcntl
import json
import os
import tempfile
from pathlib import Path

from contracts.agent_performance import (
    AgentPerformanceRecord,
    AgentPerformanceSummary,
)

# Faz 243: kritik bulgu — testler (çoğu AgentMemory() varsayılanıyla, path
# belirtmeden) gerçek "agent_memory_history/agent_memory.json"a yazıyordu.
# Bu, WeightOptimizer'ın gerçek ağırlık önerilerini hesapladığı DOSYAYA
# doğrudan test çöpü karıştırıyordu — 60.519 kayıttan 21.649'u ("(boş)"
# sembol ya da MEMWIRE/LEARN/POS... test fixture sembolleri) gerçek işlem
# değildi. Projede AYNI sınıf sorun veritabanı için zaten yaşanmış ve
# çözülmüştü (bkz. conftest.py, quantdb_test yönlendirmesi) — buradaki
# .gitignore'daki "tmp_test_memory/" satırı da bu niyetin izi ama hiç
# hayata geçirilmemişti. Artık conftest.py bu env var'ı test'lere özel bir
# dizine ayarlıyor, testler AgentMemory()'yi path belirtmeden çağırsa bile
# gerçek dosyaya asla dokunmuyor.
_DEFAULT_STORAGE_PATH = os.environ.get("AGENT_MEMORY_STORAGE_PATH", "agent_memory_history")


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
        from database.session_factory import SessionFactory

        with SessionFactory.get_session() as session:
            raw = AppSettingsRepository(session).get("reliability_legacy_cutoff_at")
        from datetime import datetime
        return datetime.fromisoformat(raw) if raw else None
    except Exception:
        return None


class AgentMemory:

    def __init__(self, storage_path: str = _DEFAULT_STORAGE_PATH):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(exist_ok=True)

        self.memory_file = self.storage_path / "agent_memory.json"
        self.lock_file = self.storage_path / "agent_memory.lock"

        self._records: dict[str, list[AgentPerformanceRecord]] = {}

        self._load()


    def _load(self):

        if not self.memory_file.exists():
            return

        raw = json.loads(self.memory_file.read_text())

        for domain, records in raw.items():
            self._records[domain] = [
                AgentPerformanceRecord.model_validate(r)
                for r in records
            ]


    def _load_from_raw(self, raw: dict):
        self._records = {}
        for domain, records in raw.items():
            self._records[domain] = [
                AgentPerformanceRecord.model_validate(r)
                for r in records
            ]

    def _write_locked(self):
        """Çağıranın zaten kilidi tuttuğu varsayılır — diske atomik yazar."""
        payload = {
            domain: [
                r.model_dump(mode="json")
                for r in records
            ]
            for domain, records in self._records.items()
        }
        fd, tmp_path = tempfile.mkstemp(
            dir=self.storage_path, prefix=".agent_memory_", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(payload, f, indent=2, default=str)
            os.replace(tmp_path, self.memory_file)
        except BaseException:
            os.unlink(tmp_path)
            raise

    def _save(self):
        # Faz 246: kritik bulgu — bu proje bir süredir aralıklı
        # "JSONDecodeError: Expecting value" flakiness'ı yaşıyordu
        # (pyproject.toml'daki bilinen-flaky rerun listesinde). Kök neden:
        # birden fazla celery worker/process aynı anda AgentMemory().record()
        # çağırdığında, write_text() dosyayı YERİNDE (in-place) baştan
        # yazıyordu — iki yazma iç içe geçerse dosya YARIM (bozuk JSON)
        # kalabiliyordu. Artık: (1) tüm süreçlerin sırayla yazmasını
        # zorlayan bir exclusive dosya kilidi (fcntl.flock), (2) önce ayrı
        # bir geçici dosyaya yazıp SONRA os.replace() ile atomik olarak
        # yerine koyma — bir okuyucu asla yarım yazılmış bir dosya görmez,
        # ya tamamen eski ya tamamen yeni içeriği görür.
        with open(self.lock_file, "w") as lockf:
            fcntl.flock(lockf, fcntl.LOCK_EX)
            try:
                self._write_locked()
            finally:
                fcntl.flock(lockf, fcntl.LOCK_UN)


    def record(
        self,
        record: AgentPerformanceRecord,
    ):
        # Faz 246 (tam doğruluk): sadece dosya bozulmasını önlemek yetmiyordu
        # — canlıda GERÇEKTEN yaşandı: bir AgentMemory örneği (ör. saatlerce
        # çalışan bir celery worker) başlangıçta yüklediği ESKİ kopyayı
        # hafızasında tutuyor, her record() çağrısında o eski kopyayı
        # (üzerine kendi yeni kaydını ekleyip) yazıp başka bir sürecin
        # arada yaptığı gerçek değişiklikleri (ör. bu oturumdaki temizlik)
        # sessizce siliyordu. Artık kilit altında DİSKTEKİ GÜNCEL hali
        # yeniden okunuyor, yeni kayıt ONA ekleniyor, öyle yazılıyor —
        # başka bir sürecin yazdığı hiçbir şey kaybolmuyor.
        domain = record.agent_domain

        with open(self.lock_file, "w") as lockf:
            fcntl.flock(lockf, fcntl.LOCK_EX)
            try:
                if self.memory_file.exists():
                    raw = json.loads(self.memory_file.read_text())
                    self._load_from_raw(raw)
                self._records.setdefault(domain, []).append(record)
                self._write_locked()
            finally:
                fcntl.flock(lockf, fcntl.LOCK_UN)


    def domains(self) -> list[str]:
        return list(self._records.keys())


    def get_summary(
        self,
        domain: str,
        window: int | None = None,
        regime: str | None = None,
        min_timestamp=None,
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
            r for r in self._records.get(domain, [])
            if (r.direction or "").upper() in ("LONG", "SHORT")
        ]

        # Faz 268b — Regime-Aware Learning: regime verilirse, SADECE o
        # piyasa rejiminde alınmış gerçek kararlar sayılır. window (aşağıda)
        # bu filtreden SONRA uygulanıyor — "bu rejimin en yeni N kaydı",
        # "tüm rejimlerin en yeni N'i sonra bu rejime göre filtrelenmiş
        # kalanı" değil.
        if regime is not None:
            records = [r for r in records if (r.market_regime or "unknown") == regime]

        # Faz 268-sonrası — kullanıcı isteği: SourceReliabilityAgent'ın
        # gerçek isabet oranına geçmesiyle birlikte eklendi (bkz. agents/
        # source_reliability_agent.py) — "reliability_legacy_cutoff_at"
        # ayarı kill_switch_legacy_cutoff_at ile AYNI Class 2 deseni: bu
        # tarihten ÖNCEKİ kayıtlar sayılmıyor, eski/bozuk mekanizmanın
        # dönemi yeni hesaba hiç karışmıyor (satırlar silinmiyor, sadece
        # dışarıda bırakılıyor).
        if min_timestamp is not None:
            records = [r for r in records if r.timestamp >= min_timestamp]

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
