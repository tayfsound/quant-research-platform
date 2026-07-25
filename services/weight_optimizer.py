"""Weight Optimizer — Bayesian smoothing ile stabil ağırlık önerisi."""

from contracts.agent_weight_snapshot import AgentWeightSnapshot
from services.agent_memory import AgentMemory
from services.weight_repository import WeightRepository


class WeightOptimizer:

    def __init__(
        self,
        agent_memory: AgentMemory,
        weight_repository: WeightRepository,
        prior_strength: int = 5,
    ):
        self.agent_memory = agent_memory
        self.weight_repository = weight_repository
        self.prior_strength = prior_strength


    def propose_weights(
        self,
        evaluation_window: int = 100,
    ) -> AgentWeightSnapshot:

        domains = self.agent_memory.domains()

        if not domains:
            return AgentWeightSnapshot(
                weights={},
                evaluation_window=evaluation_window,
            )


        proposed = {}

        for domain in domains:

            summary = self.agent_memory.get_summary(domain)

            total = summary.total_predictions
            correct = int(
                summary.overall_accuracy * total
            )


            # Bayesian smoothing
            smoothed_accuracy = (
                correct + self.prior_strength
            ) / (
                total + self.prior_strength * 2
            )


            # Sample confidence
            confidence_factor = min(
                total / evaluation_window,
                1.0
            )


            proposed[domain] = round(
                smoothed_accuracy * confidence_factor,
                3,
            )


        previous = self.weight_repository.get_latest()


        snapshot = AgentWeightSnapshot(
            weights=proposed,
            evaluation_window=evaluation_window,
            previous_snapshot_id=(
                previous.id
                if previous
                else None
            ),
        ).finalize()


        self.weight_repository.save(snapshot)

        return snapshot
