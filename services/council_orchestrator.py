"""Council Orchestrator — belief, opinions ve debate birlikte yönetilir."""
from contracts.agent import AgentOpinion, AgentDomain, DebateResult
from services.belief_engine import BeliefEngine, Belief
from services.weight_repository import WeightRepository
from services.agent_debate import AgentDebate
from agents.critics.risk_challenger import RiskChallenger


class CouncilOrchestrator:
    def __init__(self, registry, belief_engine: BeliefEngine | None = None):
        self.registry = registry
        self.belief_engine = belief_engine or BeliefEngine()
        self.weight_repository = WeightRepository()

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

        snapshot = self.weight_repository.get_latest()

        if snapshot:
            belief = self.belief_engine.apply_weights(
                opinions,
                snapshot
            )
        else:
            belief = self.belief_engine.synthesize(opinions)

        return belief, opinions
