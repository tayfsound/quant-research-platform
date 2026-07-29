"""Memory consolidator — Phase 164: Belief V3 compatible."""

from contracts.memory import EpisodicMemory, SemanticMemory, Episode
from contracts.observation import Observation, ObservationType
from contracts.belief import Belief
from database.repositories.episode_repository import EpisodeRepository
from database.repositories.observation_repository import ObservationRepository
from database.repositories.belief_repository import BeliefRepository
from services.semantic_search import SemanticSearch
from services.embedding_service import EmbeddingService
from database.connection import get_session


class MemoryConsolidator:
    def __init__(self):
        self.episodic = EpisodicMemory()
        self.semantic = SemanticMemory()
        self.search = SemanticSearch()
        self.embedder = EmbeddingService()

    def capture_cycle(self, ctx):
        self.episodic.episodes.append(Episode(
            symbol=ctx.market.symbol,
            binding_expression="",
            decision=ctx.decision.proposed_direction or "WAIT",
            outcome=ctx.outcome,
            lesson="",
        ))
        for k in ctx.cognition.relevant_knowledge:
            if k.get("type") == "observation":
                self.semantic.consolidated_beliefs.append({
                    "type": "observation",
                    "description": k.get("data", {}).get("description", ""),
                    "data": k.get("data", {}),
                })

    def commit_to_episodic(self, ctx=None):
        session = get_session()
        repo = EpisodeRepository(session)
        for ep in self.episodic.episodes:
            repo.save(ep)

    def load_from_persistent(self, session=None):
        if session is None:
            session = get_session()
        beliefs = BeliefRepository(session).get_latest(limit=100)
        for b in beliefs:
            self.semantic.consolidated_beliefs.append({
                "direction": b.get("direction"),
                "strength": b.get("strength"),
                "uncertainty": b.get("uncertainty"),
                "timestamp": b.get("timestamp"),
            })

    def memory_stats(self):
        return {
            "episodes_in_ram": len(self.episodic.episodes),
            "observations_in_ram": len(self.semantic.consolidated_beliefs),
            "consolidated_beliefs": len(self.semantic.consolidated_beliefs),
        }
