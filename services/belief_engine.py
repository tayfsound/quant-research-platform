"""Belief Engine (service) — apply_weights intrinsic_trust tabanlı."""
import math
from contracts.belief import Belief
from contracts.agent import AgentOpinion
from contracts.information_graph import InformationGraph
from contracts.agent_weight_snapshot import AgentWeightSnapshot

class BeliefEngine:
    def __init__(self, info_graph: InformationGraph | None = None):
        self.graph = info_graph or InformationGraph()

    def synthesize(self, opinions: list[AgentOpinion]) -> Belief:
        if not opinions:
            return Belief(direction="WAIT")

        agent_ids = [self._agent_domain_to_node_id(o.domain.value) for o in opinions]
        clusters: dict[str, list[AgentOpinion]] = {}

        for i, opinion in enumerate(opinions):
            root_sources = self.graph.get_root_sources(agent_ids[i])
            cluster_key = "+".join(sorted(root_sources))
            if cluster_key not in clusters:
                clusters[cluster_key] = []
            clusters[cluster_key].append(opinion)

        total_disagreement = 0.0
        cluster_count = 0
        cluster_weights: dict[str, float] = {}

        cluster_representatives: list[tuple[AgentOpinion, float, float]] = []
        for cluster_key, cluster_opinions in clusters.items():
            cluster_count += 1
            cluster_votes = {"LONG": 0.0, "SHORT": 0.0, "WAIT": 0.0}
            total_internal = 0.0
            max_trust_in_cluster = 0.0
            for o in cluster_opinions:
                w = o.effective_influence
                cluster_votes[o.direction] += w
                total_internal += w
                if w > max_trust_in_cluster:
                    max_trust_in_cluster = w

            best_dir = max(cluster_votes, key=cluster_votes.get)
            best_weight = cluster_votes[best_dir]
            second_best = max((v for k, v in cluster_votes.items() if k != best_dir), default=0.0)

            internal_disagreement = round(second_best / best_weight, 3) if best_weight > 0 else 0.0
            total_disagreement += internal_disagreement

            cluster_confidence = best_weight / total_internal if total_internal > 0 else 0.5
            rep_opinion = AgentOpinion(
                domain=cluster_opinions[0].domain,
                direction=best_dir,
                confidence=cluster_confidence,
            )
            effective_weight = round(max_trust_in_cluster * (1 - internal_disagreement), 3)
            cluster_representatives.append((rep_opinion, effective_weight, internal_disagreement))
            cluster_weights[cluster_key] = effective_weight

        avg_disagreement = round(total_disagreement / cluster_count, 3) if cluster_count > 0 else 0.0
        cluster_balance = self.graph.compute_cluster_balance(agent_ids)
        max_cluster_size = max(len(c) for c in clusters.values()) if clusters else 1
        crowding_penalty = min(round(1.0 - (1.0 / math.sqrt(max_cluster_size)), 3), 0.95) if max_cluster_size > 1 else 0.0
        coverage = len(cluster_representatives) / max(
            len(set().union(*[self.graph.get_root_sources(aid) for aid in agent_ids])), 1
        )

        weighted_votes = {"LONG": 0.0, "SHORT": 0.0, "WAIT": 0.0}
        total_weight = 0.0
        for rep, weight, _ in cluster_representatives:
            weighted_votes[rep.direction] += weight
            total_weight += weight

        if total_weight == 0:
            return Belief(direction="WAIT")

        best_direction = max(weighted_votes, key=weighted_votes.get)
        vote_strength = weighted_votes[best_direction] / total_weight
        strength = round(vote_strength * cluster_balance * coverage * (1 - crowding_penalty * 0.5), 3)

        max_other = max((v for k, v in weighted_votes.items() if k != best_direction), default=0.0)
        uncertainty = round(max_other / total_weight, 3) if total_weight > 0 else 1.0

        entropy = 0.0
        for direction in weighted_votes:
            p = weighted_votes[direction] / total_weight if total_weight > 0 else 0
            if p > 0:
                entropy -= p * math.log2(p)
        entropy = round(entropy, 3)

        supporters = [o.domain.value for o in opinions if o.direction == best_direction]
        opposers = [o.domain.value for o in opinions if o.direction != best_direction]

        evidence_paths = []
        for aid in agent_ids:
            for path in self.graph.get_paths_to_root(aid):
                evidence_paths.append(path)
        evidence_paths = sorted(set(evidence_paths))

        return Belief(
            direction=best_direction,
            strength=strength,
            uncertainty=uncertainty,
            entropy=entropy,
            information_clusters=len(cluster_representatives),
            total_opinions=len(opinions),
            cluster_disagreement=avg_disagreement,
            cluster_balance=cluster_balance,
            crowding_penalty=crowding_penalty,
            cluster_weights=cluster_weights,
            supporting_opinions=supporters,
            opposing_opinions=opposers,
            evidence_paths=evidence_paths,
        )

    def apply_weights(
        self,
        opinions: list[AgentOpinion],
        snapshot: AgentWeightSnapshot | None = None,
    ) -> Belief:
        if not snapshot or not snapshot.weights:
            return self.synthesize(opinions)

        weighted_opinions = []
        for opinion in opinions:
            domain = opinion.domain.value
            weight = snapshot.weights.get(domain, 1.0)
            adjusted = opinion.model_copy(deep=True)
            adjusted.performance_weight = weight
            adjusted.recalculate()
            weighted_opinions.append(adjusted)

        return self.synthesize(weighted_opinions)

    def _agent_domain_to_node_id(self, domain: str) -> str:
        mapping = {
            "technical": "technical_agent",
            "quant": "quant_agent",
            "order_flow": "orderflow_agent",
            "news": "news_agent",
            "macro": "macro_agent",
            "onchain": "onchain_agent",
            "sentiment": "sentiment_agent",
        }
        return mapping.get(domain, domain + "_agent")
