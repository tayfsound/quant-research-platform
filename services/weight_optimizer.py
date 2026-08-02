"""Weight Optimizer — Bayesian smoothing ile stabil ağırlık önerisi."""

from enum import Enum

from contracts.agent_weight_snapshot import AgentWeightSnapshot
from services.agent_memory import AgentMemory
from services.weight_repository import WeightRepository
from contracts.weight_approval import WeightApproval
from database.session_factory import SessionFactory
from database.repositories.weight_approval_repository import WeightApprovalRepository

MAX_WEIGHT_DELTA = 0.10


class WeightOptimizer:

    def __init__(
        self,
        agent_memory: AgentMemory,
        weight_repository: WeightRepository | None = None,
        prior_strength: int = 5,
    ):
        self.agent_memory = agent_memory

        self.weight_repository = (
            weight_repository
            if weight_repository
            else WeightRepository()
        )

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


            smoothed_accuracy = (
                correct + self.prior_strength
            ) / (
                total + self.prior_strength * 2
            )


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

    def optimize(
        self,
        agents: list[dict],
        outcome,
    ) -> dict[str, float]:
        """
        Feedback-loop weight update with a gradual delta cap.

        `outcome` is expected to expose `decision_score` in [-1, 1].
        Weight changes are clipped to MAX_WEIGHT_DELTA per decision.
        """
        current_snapshot = self.weight_repository.get_latest()
        current_weights = dict(current_snapshot.weights) if current_snapshot else {}

        decision_score = getattr(outcome, "decision_score", 0.0)

        new_weights = {}
        adjusted_domains = set()

        for agent in agents:
            domain = self._normalize_domain(agent)
            if not domain:
                continue

            adjusted_domains.add(domain)
            old_weight = current_weights.get(domain, 1.0)

            # Simple reward/penalty scaled by decision score.
            desired = old_weight + (decision_score * 0.2)
            desired = max(0.0, min(2.0, desired))

            new_weights[domain] = self._clip_delta(old_weight, desired)

        # Preserve weights for domains that did not contribute this decision.
        for domain, weight in current_weights.items():
            if domain not in new_weights:
                new_weights[domain] = weight

        return new_weights

    def _clip_delta(self, old_weight: float, new_weight: float) -> float:
        delta = new_weight - old_weight
        if abs(delta) > MAX_WEIGHT_DELTA:
            return old_weight + (MAX_WEIGHT_DELTA * (1 if delta > 0 else -1))
        return new_weight

    @staticmethod
    def _normalize_domain(agent) -> str:
        # Pydantic model veya dict olabilir
        if hasattr(agent, "model_dump"):
            data = agent.model_dump()
        elif hasattr(agent, "dict"):
            data = agent.dict()
        elif isinstance(agent, dict):
            data = agent
        else:
            data = {}

        domain = data.get("domain") or data.get("agent_id") or "unknown"
        if isinstance(domain, Enum):
            domain = domain.value
        if isinstance(domain, dict):
            domain = domain.get("value", "unknown")
        return str(domain).lower()
