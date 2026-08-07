"""Agent Memory — persistent storage backed by JSON."""

import json
import os
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


class AgentMemory:

    def __init__(self, storage_path: str = _DEFAULT_STORAGE_PATH):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(exist_ok=True)

        self.memory_file = self.storage_path / "agent_memory.json"

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


    def _save(self):

        payload = {
            domain: [
                r.model_dump(mode="json")
                for r in records
            ]
            for domain, records in self._records.items()
        }

        self.memory_file.write_text(
            json.dumps(
                payload,
                indent=2,
                default=str,
            )
        )


    def record(
        self,
        record: AgentPerformanceRecord,
    ):

        domain = record.agent_domain

        self._records.setdefault(
            domain,
            [],
        ).append(record)

        self._save()


    def domains(self) -> list[str]:
        return list(self._records.keys())


    def get_summary(
        self,
        domain: str,
    ) -> AgentPerformanceSummary:

        records = self._records.get(domain, [])

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
