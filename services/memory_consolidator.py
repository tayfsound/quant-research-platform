"""Memory consolidator — Phase 164: Belief V3 compatible."""

from contracts.memory import Episode, EpisodicMemory, SemanticMemory, WorkingMemory
from database.connection import get_session
from database.repositories.belief_repository import BeliefRepository
from database.repositories.episode_repository import EpisodeRepository
from services.embedding_service import EmbeddingService
from services.semantic_search import SemanticSearch


class MemoryConsolidator:
    def __init__(self):
        # Gap #8: MemoryEngine.execute() referenced self.consolidator.working
        # (a WorkingMemory) but this class never constructed one — another
        # AttributeError that only surfaced the moment MemoryEngine was
        # actually invoked for the first time (never, until this fix).
        self.working = WorkingMemory()
        self.episodic = EpisodicMemory()
        self.semantic = SemanticMemory()
        self.search = SemanticSearch()
        self.embedder = EmbeddingService()
        # Gap #8: commit_to_episodic() used to loop over ALL of
        # self.episodic.episodes on every call (restored history included)
        # and re-INSERT every one of them — never actually a problem before
        # because nothing ever called it more than once (nothing called it
        # at all), but a real bug the moment this gets wired into a live,
        # repeatedly-run pipeline: every cycle would re-insert the entire
        # accumulated history as new duplicate rows. Tracks what's already
        # in the DB so only genuinely new episodes get saved.
        self._committed_ids: set = set()
        self._restore_episodic()


    def _restore_episodic(self):
        session = get_session()
        try:
            rows = EpisodeRepository(session).latest(limit=100)

            for row in rows:
                data = dict(row)

                if isinstance(data.get("outcome"), str):
                    import json
                    data["outcome"] = json.loads(data["outcome"])

                if isinstance(data.get("embedding"), str):
                    import json
                    try:
                        data["embedding"] = json.loads(data["embedding"])
                    except Exception:
                        data["embedding"] = None

                episode = Episode(**data)
                self.episodic.episodes.append(episode)
                self._committed_ids.add(episode.id)
        finally:
            session.close()

    def capture_cycle(self, ctx):
        self.working.add_observation({
            "cycle_id": str(ctx.cycle_id),
            "symbol": ctx.market.symbol,
            "decision": ctx.decision.proposed_direction or "WAIT",
            "features": ctx.market.features,
        })
        self.episodic.episodes.append(Episode(
            cycle_id=ctx.cycle_id,
            symbol=ctx.market.symbol,
            observation={"features": ctx.market.features},
            binding_expression="",
            decision=ctx.decision.proposed_direction or "WAIT",
            outcome=(
                ctx.outcome.model_dump(mode="json")
                if hasattr(ctx.outcome, "model_dump")
                else ctx.outcome
            ),
            lesson="",
        ))
        for k in ctx.cognition.relevant_knowledge:
            if k.get("type") == "observation":
                self.semantic.consolidated_beliefs.append({
                    "type": "observation",
                    "description": k.get("data", {}).get("description", ""),
                    "data": k.get("data", {}),
                })

    def record_real_episode(
        self,
        *,
        cycle_id,
        symbol: str,
        features: dict,
        decision: str,
        outcome: dict,
        lesson: str = "",
    ):
        """Faz 268aj — kullanıcı isteği: episodic memory GERÇEK verilerle
        beslensin. capture_cycle()'ın aksine (canlı cycle sırasında,
        sonucu henüz belli olmayan ctx'ten çağrılıyor, Faz 268j'den beri
        hiç kullanılmıyor — bkz. CognitiveEngine.finalize()'daki not) bu
        SADECE gerçekten kapanmış bir pozisyondan (services/
        position_closer.py), gerçek pnl/win ile çağrılıyor. Faz 268j'nin
        kapattığı sızıntı (sahte n-bar proxy ile hafızayı kirletme) burada
        tekrarlanmıyor — outcome her zaman gerçek kapanıştan geliyor."""
        episode = Episode(
            cycle_id=cycle_id,
            symbol=symbol,
            observation={"features": features},
            binding_expression="",
            decision=decision,
            outcome=outcome,
            lesson=lesson,
        )
        self.episodic.episodes.append(episode)
        return self.commit_to_episodic()

    def commit_to_episodic(self, ctx=None):
        session = get_session()
        saved = None
        try:
            repo = EpisodeRepository(session)

            # Gap #8/#16: episodes used to be written with embedding=None
            # always (nothing ever called EmbeddingService.encode_episode()
            # before save()), so semantic search (`WHERE embedding IS NOT
            # NULL`) could never find anything this consolidator ever wrote.
            for ep in self.episodic.episodes:
                if ep.id in self._committed_ids:
                    continue
                embedding = self.embedder.encode_episode(ep.model_dump(mode="json"))
                saved = repo.save(ep, embedding=embedding)
                self._committed_ids.add(ep.id)
        finally:
            session.close()

        return saved

    def consolidate_if_ready(self, threshold: int = 10):
        """Gap #8: MemoryEngine.execute() called this but it never existed
        on this class — an AttributeError waiting to happen the moment
        MemoryEngine was ever actually invoked (which it never was)."""
        self.semantic.consolidate(self.episodic, threshold=threshold)

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
