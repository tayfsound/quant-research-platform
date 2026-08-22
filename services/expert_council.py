"""Expert Council V2 — bağlama duyarlı ağırlıklandırma."""
from contracts.agent import AgentDomain, AgentOpinion, BaseAgent
from services.agent_memory import AgentMemory


class ExpertCouncil:
    def __init__(self, agent_memory: AgentMemory):
        self.agents: dict[str, BaseAgent] = {}
        self.memory = agent_memory
        self.dependency_groups: dict[str, list[str]] = {}  # group -> [agent_ids]

    def register(self, agent: "BaseAgent", dependency_group: str = ""):
        self.agents[agent.domain.value] = agent
        if dependency_group:
            if dependency_group not in self.dependency_groups:
                self.dependency_groups[dependency_group] = []
            self.dependency_groups[dependency_group].append(agent.domain.value)

    def deliberate(self, context: dict) -> list[AgentOpinion]:
        opinions = []
        for agent in self.agents.values():
            try:
                opinion = agent.analyze(context)
                opinions.append(opinion)
            except Exception as e:
                opinions.append(AgentOpinion(
                    domain=AgentDomain.TECHNICAL,
                    direction="WAIT",
                    confidence=0.0,
                    evidence=[],
                    uncertainty=1.0,
                    caveats=[f"Agent error: {str(e)}"],
                ))
        return opinions

    def synthesize(self, opinions: list[AgentOpinion], market_regime: str = "") -> AgentOpinion:
        if not opinions:
            return AgentOpinion(domain=AgentDomain.EXECUTIVE, direction="WAIT", confidence=0.0)

        # Grup başına en fazla 1 oy (bağımsızlık kontrolü)
        group_votes: dict[str, dict[str, float]] = {}  # group -> {direction: max_weight}
        independent_opinions = []
        for opinion in opinions:
            group = self._get_dependency_group(opinion.domain.value)
            if group:
                if group not in group_votes:
                    group_votes[group] = {"LONG": 0.0, "SHORT": 0.0, "WAIT": 0.0}
                contextual_weight = self.memory.get_contextual_confidence(
                    opinion.domain.value, market_regime,
                )
                weight = opinion.confidence * contextual_weight
                if weight > group_votes[group].get(opinion.direction, 0.0):
                    group_votes[group][opinion.direction] = weight
            else:
                independent_opinions.append(opinion)

        # Bağımsız agent'lar + grup temsilcileri
        weighted_votes = {"LONG": 0.0, "SHORT": 0.0, "WAIT": 0.0}
        total_weight = 0.0

        for opinion in independent_opinions:
            contextual_weight = self.memory.get_contextual_confidence(
                opinion.domain.value, market_regime,
            )
            weight = opinion.confidence * contextual_weight
            weighted_votes[opinion.direction] += weight
            total_weight += weight

        # Grup temsilcilerini ekle
        for group, votes in group_votes.items():
            for direction, weight in votes.items():
                weighted_votes[direction] += weight
                total_weight += weight

        if total_weight == 0:
            return AgentOpinion(domain=AgentDomain.EXECUTIVE, direction="WAIT", confidence=0.0)

        best_direction = max(weighted_votes, key=weighted_votes.get)
        confidence = weighted_votes[best_direction] / total_weight if total_weight > 0 else 0.0

        return AgentOpinion(
            domain=AgentDomain.EXECUTIVE,
            direction=best_direction,
            confidence=round(confidence, 3),
            evidence=[f"Context-aware weighted votes: {weighted_votes}"],
        )

    def _get_dependency_group(self, domain: str) -> str:
        for group, members in self.dependency_groups.items():
            if domain in members:
                return group
        return ""
