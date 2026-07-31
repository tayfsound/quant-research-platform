"""Agent Debate Layer V2 — çok turlu tartışma + Cognitive Audit."""
from contracts.agent import (
    AgentChallenge,
    AgentDomain,
    AgentOpinion,
    AgentResponse,
    ChallengerAgent,
    CognitiveAudit,
    DebateResult,
    DebateRound,
    ResponderAgent,
)


class AgentDebate:
    def __init__(self, max_rounds: int = 2):
        self.challengers: dict[str, ChallengerAgent] = {}
        self.responders: dict[str, ResponderAgent] = {}
        self.max_rounds = max_rounds

    def register_challenger(self, domain: AgentDomain, agent: "ChallengerAgent"):
        self.challengers[domain.value] = agent

    def register_responder(self, domain: AgentDomain, agent: "ResponderAgent"):
        self.responders[domain.value] = agent

    def run_debate(self, opinions: list[AgentOpinion], context: dict) -> DebateResult:
        rounds: list[DebateRound] = []
        adjusted_confidence: dict[str, float] = {
            o.domain.value: o.confidence for o in opinions
        }

        # Çok turlu tartışma
        for round_num in range(1, self.max_rounds + 1):
            challenges: list[AgentChallenge] = []
            responses: list[AgentResponse] = []

            # Challenger'lar itiraz üretir
            for challenger in self.challengers.values():
                for opinion in opinions:
                    try:
                        result = challenger.challenge(opinion, context)
                        if result:
                            challenges.extend(result)
                    except Exception:
                        pass

            # Responder'lar cevap verir
            for challenge in challenges:
                responder = self.responders.get(challenge.target_domain.value)
                if responder:
                    try:
                        response = responder.respond(challenge, context)
                        responses.append(response)
                        # Confidence ayarı
                        key = challenge.target_domain.value
                        if key in adjusted_confidence:
                            adjusted_confidence[key] = max(
                                0.1,
                                adjusted_confidence[key] + response.confidence_change,
                            )
                    except Exception:
                        pass

            rounds.append(DebateRound(
                round_number=round_num,
                challenges=challenges,
                responses=responses,
            ))

        # Cognitive Audit (Alter Ego)
        audit = self._run_cognitive_audit(opinions, rounds)

        # Sentez
        final = self._synthesize(opinions, adjusted_confidence)

        return DebateResult(
            original_opinions=opinions,
            rounds=rounds,
            cognitive_audit=audit,
            final_direction=final.direction,
            final_confidence=final.confidence,
            reasoning=self._generate_reasoning(opinions, rounds, audit, final),
        )

    def _run_cognitive_audit(
        self, opinions: list[AgentOpinion], rounds: list[DebateRound],
    ) -> CognitiveAudit | None:
        alter_ego = self.challengers.get(AgentDomain.ALTER_EGO.value)
        if not alter_ego:
            return None

        # Alter Ego'dan audit iste
        try:
            audit_opinion = AgentOpinion(
                domain=AgentDomain.EXECUTIVE,
                direction="WAIT",
                confidence=0.5,
            )
            challenges = alter_ego.challenge(audit_opinion, {
                "opinions": [o.model_dump() for o in opinions],
                "rounds": [r.model_dump() for r in rounds],
            })
        except Exception:
            return CognitiveAudit()

        # Challenge'lardan CognitiveAudit üret
        if not challenges:
            return CognitiveAudit()

        return CognitiveAudit(
            confirmation_bias=round(
                sum(c.confidence for c in challenges if "bias" in c.reason.lower()) /
                max(len(challenges), 1), 3
            ),
            herd_behavior_risk=round(
                sum(c.confidence for c in challenges if "herd" in c.reason.lower()) /
                max(len(challenges), 1), 3
            ),
            overconfidence_risk=round(
                sum(c.confidence for c in challenges if "confidence" in c.reason.lower()) /
                max(len(challenges), 1), 3
            ),
            missing_information=[c.reason for c in challenges],
            recommended_action=challenges[0].suggested_adjustment if challenges else "",
        )

    def _synthesize(
        self, opinions: list[AgentOpinion], adjusted_confidence: dict[str, float],
    ) -> AgentOpinion:
        weighted_votes = {"LONG": 0.0, "SHORT": 0.0, "WAIT": 0.0}
        total_weight = 0.0

        for opinion in opinions:
            weight = adjusted_confidence.get(opinion.domain.value, opinion.confidence)
            weighted_votes[opinion.direction] += weight
            total_weight += weight

        if total_weight == 0:
            return AgentOpinion(domain=AgentDomain.EXECUTIVE, direction="WAIT", confidence=0.0)

        best_direction = max(weighted_votes, key=weighted_votes.get)
        confidence = weighted_votes[best_direction] / total_weight if total_weight > 0 else 0.0

        return AgentOpinion(
            domain=AgentDomain.EXECUTIVE,
            direction=best_direction,
            confidence=round(confidence, 3),
        )

    def _generate_reasoning(
        self, opinions, rounds, audit, final,
    ) -> str:
        parts = [f"Final: {final.direction} (conf {final.confidence})"]
        total_challenges = sum(len(r.challenges) for r in rounds)
        if total_challenges:
            parts.append(f"{total_challenges} challenges across {len(rounds)} rounds")
        if audit:
            if audit.overconfidence_risk > 0.5:
                parts.append("⚠️ Overconfidence risk detected")
            if audit.herd_behavior_risk > 0.5:
                parts.append("⚠️ Herd behavior risk detected")
        return " | ".join(parts)
