"""Council Orchestrator — belief, opinions ve debate birlikte yönetilir."""
from agents.critics.risk_challenger import RiskChallenger
from contracts.agent import AgentDomain, AgentOpinion, DebateResult
from services.agent_debate import AgentDebate
from services.belief_engine import Belief, BeliefEngine
from services.weight_repository import WeightRepository


class CouncilOrchestrator:
    def __init__(
        self,
        registry,
        belief_engine: BeliefEngine | None = None,
        pinned_weight_snapshot_id=None,
    ):
        self.registry = registry
        self.belief_engine = belief_engine or BeliefEngine()
        self.weight_repository = WeightRepository()
        self.active_weight_snapshot_id = None
        # If set, deliberate() uses this exact snapshot instead of
        # get_latest() — required for backtest determinism, otherwise a
        # decision simulated for a past bar would use weights learned from
        # data that (in a real run) wouldn't exist yet.
        self.pinned_weight_snapshot_id = pinned_weight_snapshot_id

        self.last_debate_result: DebateResult | None = None

        self.debate = AgentDebate(max_rounds=2)
        self.debate.register_challenger(
            AgentDomain.RISK,
            RiskChallenger()
        )

    def deliberate(
        self,
        contexts: dict[AgentDomain, object]
    ) -> tuple[Belief, list[AgentOpinion]]:

        opinions: list[AgentOpinion] = []

        for domain, ctx in contexts.items():
            if ctx is None:
                continue

            agent = self.registry.get(domain)
            if not agent:
                continue

            try:
                opinion = agent.analyze(ctx)
                opinions.append(opinion)

            except Exception as e:
                print(f"[Council] {domain} agent failed: {e}")

        if not opinions:
            self.last_debate_result = None
            return Belief(direction="WAIT", total_opinions=0), []

        self.last_debate_result = self.debate.run_debate(
            opinions,
            {}
        )

        if self.pinned_weight_snapshot_id is not None:
            snapshot = self.weight_repository.get_by_id(self.pinned_weight_snapshot_id)
        else:
            snapshot = self.weight_repository.get_latest()
        self.active_weight_snapshot_id = snapshot.id if snapshot else None

        if snapshot:
            belief = self.belief_engine.apply_weights(
                opinions,
                snapshot
            )
        else:
            belief = self.belief_engine.synthesize(opinions)

        return belief, opinions
