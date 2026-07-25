"""Weight Optimizer — Bayesian smoothing ile stabil ağırlık önerisi."""
from contracts.agent_weight_snapshot import AgentWeightSnapshot
from services.agent_memory import AgentMemory

class WeightOptimizer:
    def __init__(self, agent_memory: AgentMemory, prior_strength: int = 5):
        self.agent_memory = agent_memory
        self.prior_strength = prior_strength
        self.current_snapshot: AgentWeightSnapshot | None = None

    def propose_weights(self, evaluation_window: int = 100) -> AgentWeightSnapshot:
        domains = self.agent_memory.domains()
        if not domains:
            return AgentWeightSnapshot(weights={}, evaluation_window=evaluation_window)

        proposed = {}
        for domain in domains:
            summary = self.agent_memory.get_summary(domain)
            total = summary.total_predictions
            correct = int(summary.overall_accuracy * total)
            
            # Bayesian smoothing: (wins + prior) / (total + prior * 2)
            smoothed_accuracy = (correct + self.prior_strength) / (total + self.prior_strength * 2) if total > 0 else 1.0
            
            # Düşük örneklem cezası
            confidence_factor = min(total / evaluation_window, 1.0) if evaluation_window > 0 else 1.0
            
            proposed[domain] = round(smoothed_accuracy * confidence_factor, 3)

        snapshot = AgentWeightSnapshot(
            weights=proposed,
            evaluation_window=evaluation_window,
            previous_snapshot_id=self.current_snapshot.id if self.current_snapshot else None,
        ).finalize()

        self.current_snapshot = snapshot
        return snapshot
