"""Kalıcı hafıza testleri."""
from contracts.memory import Episode
from contracts.observation import Observation, ObservationType
from contracts.belief import Belief
from services.belief_engine import BeliefEngine
from contracts.curiosity import ExperimentProposal, ExperimentStatus
from contracts.evaluation import Lesson
from contracts.context import CognitiveCycleContext
from database.connection import get_session
from database.repositories.episode_repository import EpisodeRepository
from database.repositories.observation_repository import ObservationRepository
from database.repositories.belief_repository import BeliefRepository
from database.repositories.experiment_repository import ExperimentRepository
from database.repositories.lesson_repository import LessonRepository
from services.memory_consolidator import MemoryConsolidator
from services.semantic_search import SemanticSearch
from services.memory_service import MemoryService

def test_save_and_retrieve_episode():
    session = get_session()
    repo = EpisodeRepository(session)
    episode = Episode(
        symbol="BTCUSDT",
        binding_expression="RSI < 30",
        decision="LONG",
        outcome={"pnl": 100},
        lesson="Test lesson",
    )
    repo.save(episode)
    rows = repo.latest(limit=1)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "BTCUSDT"

def test_save_and_retrieve_observation():
    session = get_session()
    repo = ObservationRepository(session)
    obs = Observation(
        type=ObservationType.INDICATOR,
        symbol="BTCUSDT",
        timeframe="4H",
        description="RSI oversold",
        data={"rsi": 25},
    )
    repo.save(obs)
    rows = repo.latest(limit=1)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "BTCUSDT"

def test_save_and_update_belief():
    session = get_session()
    repo = BeliefRepository(session)
    belief = Belief(
        direction="LONG",
        strength=0.7,
    )
    repo.save(belief)
    row = repo.get_by_expression("")
    assert row is not None

def test_experiment_lifecycle():
    session = get_session()
    repo = ExperimentRepository(session)
    proposal = ExperimentProposal(
        hypothesis="RSI < 30 oversold test",
        test_expression="RSI < 30",
        estimated_value=0.8,
        status=ExperimentStatus.PROPOSED,
    )
    repo.save(proposal)
    repo.update_status(str(proposal.id), ExperimentStatus.RUNNING)
    repo.update_status(str(proposal.id), ExperimentStatus.COMPLETED, {"win_rate": 0.65, "samples": 200})
    rows = repo.latest(limit=1)
    assert len(rows) == 1
    assert rows[0]["status"] == "completed"

def test_agent_remembers_after_restart():
    cons1 = MemoryConsolidator()
    ctx = CognitiveCycleContext(
        market={"symbol": "BTCUSDT", "timeframe": "4H", "features": {"RSI": 25}},
        decision={"proposed_direction": "LONG", "proposed_size": 0.5},
        outcome={"executed": True, "pnl": 100},
    )
    ctx.cognition.relevant_knowledge.append({
        "type": "cognitive_binding",
        "data": {"expression": {"description": "RSI < 30"}}
    })
    cons1.capture_cycle(ctx)
    cons1.commit_to_episodic(ctx)
    cons2 = MemoryConsolidator()
    assert len(cons2.episodic.episodes) >= 1
    assert any(e.symbol == "BTCUSDT" for e in cons2.episodic.episodes)

def test_full_memory_stats():
    cons = MemoryConsolidator()
    stats = cons.memory_stats()
    assert "episodes_in_ram" in stats
    assert stats["episodes_in_ram"] >= 0

def test_memory_service_stats():
    svc = MemoryService()
    stats = svc.stats()
    assert "episodes_in_ram" in stats
    assert stats["episodes_in_ram"] >= 0

def test_embedding_generation():
    from services.embedding_service import EmbeddingService
    svc = EmbeddingService()
    vec = svc.encode_features({"RSI": 25, "ATR": 3}, "BTCUSDT")
    assert len(vec) == 384
    assert all(isinstance(v, float) for v in vec)

def test_semantic_search_finds_similar():
    cons = MemoryConsolidator()
    ctx = CognitiveCycleContext(
        market={"symbol": "BTCUSDT", "timeframe": "4H", "features": {"RSI": 25, "ATR": 3}},
        decision={"proposed_direction": "LONG", "proposed_size": 0.5},
        outcome={"executed": True, "pnl": 100},
    )
    ctx.cognition.relevant_knowledge.append({
        "type": "cognitive_binding",
        "data": {"expression": {"description": "RSI < 30"}}
    })
    cons.capture_cycle(ctx)
    cons.commit_to_episodic(ctx)
    search = SemanticSearch()
    results = search.find_similar_episodes({"RSI": 25, "ATR": 3}, symbol="BTCUSDT", limit=3)
    assert len(results) >= 1
    assert results[0]["symbol"] == "BTCUSDT"
    assert results[0]["similarity"] > 0

def test_vector_memory_search():
    cons = MemoryConsolidator()
    ctx = CognitiveCycleContext(
        market={"symbol": "BTCUSDT", "timeframe": "4H", "features": {"RSI": 25, "ATR": 3}},
        decision={"proposed_direction": "LONG", "proposed_size": 0.5},
        outcome={"executed": True, "pnl": 100},
    )
    ctx.cognition.relevant_knowledge.append({
        "type": "cognitive_binding",
        "data": {"expression": {"description": "RSI < 30"}}
    })
    cons.capture_cycle(ctx)
    cons.commit_to_episodic(ctx)
    search = SemanticSearch()
    results = search.find_similar_episodes({"RSI": 25, "ATR": 3}, symbol="BTCUSDT", limit=3)
    assert isinstance(results, list)
    if results:
        assert results[0]["symbol"] == "BTCUSDT"
