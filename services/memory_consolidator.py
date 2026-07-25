"""Memory Consolidator — embedding RAM'e alınır, Episode modelinde saklanır."""
from uuid import UUID
from contracts.memory import WorkingMemory, EpisodicMemory, SemanticMemory, Episode
from contracts.context import CognitiveCycleContext
from contracts.belief import Belief
from database.session_factory import SessionFactory
from database.repositories.episode_repository import EpisodeRepository
from database.repositories.belief_repository import BeliefRepository
from services.embedding_service import EmbeddingService
import json

class MemoryConsolidator:
    def __init__(self):
        self.working = WorkingMemory()
        self.episodic = EpisodicMemory()
        self.semantic = SemanticMemory()
        self.embedder = EmbeddingService()
        self.load_state()

    def load_state(self):
        try:
            with SessionFactory.get_session() as session:
                repo = EpisodeRepository(session)
                rows = list(reversed(repo.latest(limit=1000)))
                for row in rows:
                    episode = Episode(
                        id=UUID(str(row["id"])),
                        cycle_id=UUID(str(row["cycle_id"])) if row["cycle_id"] else None,
                        symbol=row["symbol"],
                        observation=row["observation"] if isinstance(row["observation"], dict) else json.loads(row["observation"] or "{}"),
                        binding_expression=row["binding_expression"] or "",
                        decision=row["decision"] or "",
                        outcome=row["outcome"] if isinstance(row["outcome"], dict) else json.loads(row["outcome"] or "{}"),
                        lesson=row["lesson"] or "",
                    )
                    self.episodic.add_episode(episode)
        except Exception as e:
            print(f"⚠️ Episode reload failed: {e}")

        try:
            with SessionFactory.get_session() as session:
                repo = BeliefRepository(session)
                beliefs = repo.all()
                for b in beliefs:
                    self.semantic.consolidated_beliefs.append({
                        "expression": b["expression"],
                        "confidence": b["confidence"],
                        "evidence_count": b["evidence_count"],
                    })
                if beliefs:
                    self.semantic.total_episodes = sum(b["evidence_count"] for b in beliefs)
        except Exception as e:
            print(f"⚠️ Belief reload failed: {e}")

    def capture_cycle(self, ctx: CognitiveCycleContext):
        for item in ctx.cognition.relevant_knowledge:
            self.working.add_observation(item)

    def commit_to_episodic(self, ctx: CognitiveCycleContext) -> Episode | None:
        if not self.working.observations:
            return None
        binding_expr = ""
        for obs in self.working.observations:
            if obs.get("type") == "cognitive_binding" and "data" in obs:
                binding_expr = obs["data"].get("expression", {}).get("description", "")
        episode = Episode(
            cycle_id=ctx.cycle_id,
            symbol=ctx.market.symbol,
            observation={"features": ctx.market.features, "timeframe": ctx.market.timeframe},
            binding_expression=binding_expr,
            decision=ctx.decision.final_direction,
            outcome=ctx.outcome.model_dump() if hasattr(ctx.outcome, "model_dump") else ctx.outcome,
        )
        embedding = self.embedder.encode_episode({
            "symbol": episode.symbol,
            "decision": episode.decision,
            "binding_expression": episode.binding_expression,
            "observation": episode.observation,
            "outcome": episode.outcome,
        })
        episode.embedding = embedding
        self.episodic.add_episode(episode)
        with SessionFactory.get_session() as session:
            EpisodeRepository(session).save(episode, embedding)
        self.working.clear()
        return episode

    def consolidate_if_ready(self) -> bool:
        if len(self.episodic.episodes) >= 10:
            self.semantic.consolidate(self.episodic)
            with SessionFactory.get_session() as session:
                repo = BeliefRepository(session)
                for belief_data in self.semantic.consolidated_beliefs:
                    belief = Belief(
                        statement=belief_data.get("expression", ""),
                        expression=belief_data.get("expression", ""),
                        category="consolidated",
                        confidence=belief_data.get("confidence", 0.5),
                        evidence_count=belief_data.get("evidence_count", 0),
                    )
                    repo.save(belief)
            return True
        return False

    def replay_experiences(self, n: int = 5, seed: int | None = None) -> list[Episode]:
        return self.episodic.sample(n, seed)

    def memory_stats(self) -> dict:
        return {
            "episodes_in_ram": len(self.episodic.episodes),
            "beliefs_in_ram": len(self.semantic.consolidated_beliefs),
        }
