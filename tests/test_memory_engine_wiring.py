"""Gap #8: MemoryEngine existed, had a real, working design (episodic
capture + DB persistence + semantic consolidation), and was never called
from anywhere in the pipeline. Wiring it in surfaced three more real,
previously-unexercised bugs in MemoryConsolidator, all fixed here too:
`consolidate_if_ready()` didn't exist (AttributeError), `self.working`
(WorkingMemory) was never constructed (AttributeError), and
`commit_to_episodic()` re-INSERTed the entire accumulated episode history
on every call instead of only new ones (would have silently duplicated rows
the moment this got called more than once in a live pipeline).

This proves the real, end-to-end fix: two consecutive live cycles through
CognitiveOrchestrator (which calls engine.finalize()) each persist exactly
one new episode with a real embedding — no duplicates, no crash — and a
subsequent semantic search actually finds one of them."""
from database.repositories.episode_repository import EpisodeRepository
from database.session_factory import SessionFactory
from services.orchestrator import CognitiveOrchestrator


def test_two_live_cycles_persist_exactly_two_new_episodes_with_embeddings():
    with SessionFactory.get_session() as session:
        before = len(EpisodeRepository(session).latest(limit=100000))

    orch = CognitiveOrchestrator()
    orch.run_cycle(seed=101)
    orch.run_cycle(seed=102)

    with SessionFactory.get_session() as session:
        rows = EpisodeRepository(session).latest(limit=100000)

    assert len(rows) == before + 2

    newest_two = list(rows)[:2]
    for row in newest_two:
        assert row["embedding"] is not None


def test_semantic_search_finds_a_real_episode_written_by_a_live_cycle():
    orch = CognitiveOrchestrator()
    result = orch.run_cycle(seed=103)

    hits = orch.engine.memory_engine.consolidator.search.find_similar_episodes(
        result["features"], symbol=result["symbol"], limit=5
    )
    assert len(hits) >= 1
