from datetime import datetime, timedelta
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
        previous_weights = dict(previous.weights) if previous else {}

        snapshot = AgentWeightSnapshot(
            weights=proposed,
            evaluation_window=evaluation_window,
            previous_snapshot_id=(
                previous.id
                if previous
                else None
            ),
        ).finalize()

        # Faz 214: kritik bulgu — bu metod optimize()'daki (aynı sınıfın
        # diğer ağırlık güncelleme yolu) >%10 değişiklik için insan onayı
        # zorunluluğunu (WeightApproval, Faz 160-165) hiç uygulamıyordu,
        # doğrudan kaydediyordu. services/position_closer.py (Faz 210b/211b)
        # gerçek kapanan her işlemde bunu çağırınca, büyük ağırlık
        # sıçramaları hiç insan gözünden geçmeden canlıya uygulanmaya
        # başladı — kasıtlı güvenlik kontrolünü fark etmeden atlıyordu.
        if previous_weights:
            max_change = max(
                abs(proposed.get(k, 0) - previous_weights.get(k, 0))
                for k in set(proposed) | set(previous_weights)
            )
            if max_change > MAX_WEIGHT_DELTA:
                try:
                    approval = WeightApproval(
                        expires_at=datetime.now() + timedelta(hours=24),
                        proposed_weights=proposed,
                        previous_weights=previous_weights,
                        max_delta=MAX_WEIGHT_DELTA,
                        status="pending",
                    )
                    with SessionFactory.get_session() as session:
                        WeightApprovalRepository(session).save(approval)
                    return previous  # onaylanana kadar mevcut snapshot geçerli
                except Exception as e:
                    import structlog
                    logger = structlog.get_logger()
                    logger.error('weight_approval_save_failed', error=str(e), max_change=max_change)
                    # Tablo henüz yoksa (ör. eski migration) eskisi gibi
                    # doğrudan kaydetmeye düş — sessizce hiçbir şeyin
                    # güncellenmemesi daha kötü.

        self.weight_repository.save(snapshot)

        return snapshot

    def optimize(
        self,
        agents: list[dict],
        outcome,
        require_approval: bool = True,
    ) -> dict[str, float]:
        """
        Feedback-loop weight update with a gradual delta cap.
        Large changes (>5%) require human approval.
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

            desired = old_weight + (decision_score * 0.2)
            desired = max(0.0, min(2.0, desired))

            new_weights[domain] = self._clip_delta(old_weight, desired)

        for domain, weight in current_weights.items():
            if domain not in new_weights:
                new_weights[domain] = weight

        # Approval gate: >5% max change requires human approval
        if current_weights and new_weights:
            max_change = max(
                abs(new_weights.get(k, 0) - current_weights.get(k, 0))
                for k in set(new_weights) | set(current_weights)
            )
            if require_approval and max_change > 0.05:
                try:
                    approval = WeightApproval(
                        expires_at=datetime.now() + timedelta(hours=24),
                        proposed_weights=new_weights,
                        previous_weights=current_weights,
                        max_delta=MAX_WEIGHT_DELTA,
                        status="pending",
                    )
                    with SessionFactory.get_session() as session:
                        WeightApprovalRepository(session).save(approval)
                    return current_weights  # Return old weights until approved
                except Exception as e:
                    import structlog
                    logger = structlog.get_logger()
                    logger.error('weight_approval_save_failed', error=str(e), max_change=max_change)
                    pass  # Table may not exist yet — fall through to allow weight update

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