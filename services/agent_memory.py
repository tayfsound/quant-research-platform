"""Agent Memory — public API (domains metodu)."""
from contracts.agent_performance import AgentPerformanceRecord, AgentPerformanceSummary

class AgentMemory:
    def __init__(self):
        self._records: dict[str, list[AgentPerformanceRecord]] = {}

    def record(self, record: AgentPerformanceRecord):
        domain = record.agent_domain
        if domain not in self._records:
            self._records[domain] = []
        self._records[domain].append(record)

    def domains(self) -> list[str]:
        return list(self._records.keys())

    def get_summary(self, domain: str) -> AgentPerformanceSummary:
        records = self._records.get(domain, [])
        if not records:
            return AgentPerformanceSummary(agent_domain=domain)

        total = len(records)
        correct = sum(1 for r in records if r.was_correct)
        overall = correct / total if total > 0 else 0.0

        by_regime: dict[str, list[bool]] = {}
        for r in records:
            regime = str(r.market_regime) if r.market_regime else "unknown"
            if regime not in by_regime:
                by_regime[regime] = []
            by_regime[regime].append(r.was_correct)

        regime_accuracy = {
            regime: sum(results) / len(results)
            for regime, results in by_regime.items()
            if results
        }

        recent = records[-20:]
        recent_accuracy = sum(1 for r in recent if r.was_correct) / len(recent) if recent else 0.0

        return AgentPerformanceSummary(
            agent_domain=domain,
            overall_accuracy=round(overall, 3),
            total_predictions=total,
            by_regime=regime_accuracy,
            recent_accuracy=round(recent_accuracy, 3),
        )

    def get_contextual_confidence(self, domain: str, market_regime: str = "") -> float:
        summary = self.get_summary(domain)
        if summary.total_predictions < 5:
            return 0.5
        regime_acc = summary.by_regime.get(market_regime, summary.overall_accuracy)
        return round(regime_acc * 0.5 + summary.overall_accuracy * 0.3 + summary.recent_accuracy * 0.2, 3)
