"""Memory Service — güncel SemanticSearch API ile."""
from contracts.belief import Belief
from contracts.curiosity import ExperimentProposal
from contracts.evaluation import Lesson
from contracts.memory import Episode
from database.repositories.belief_repository import BeliefRepository
from database.repositories.episode_repository import EpisodeRepository
from database.repositories.experiment_repository import ExperimentRepository
from database.repositories.lesson_repository import LessonRepository
from database.session_factory import SessionFactory
from services.memory_consolidator import MemoryConsolidator
from services.semantic_search import SemanticSearch


class MemoryService:
    def __init__(self):
        self.consolidator = MemoryConsolidator()
        self.search = SemanticSearch()

    def stats(self) -> dict:
        return self.consolidator.memory_stats()

    def find_similar(self, features: dict[str, float], symbol: str | None = None, limit: int = 10) -> list[dict]:
        return self.search.find_similar_episodes(features, symbol, limit)

    def store_episode(self, episode: Episode):
        with SessionFactory.get_session() as session:
            EpisodeRepository(session).save(episode)

    def store_belief(self, belief: Belief):
        with SessionFactory.get_session() as session:
            BeliefRepository(session).save(belief)

    def store_experiment(self, proposal: ExperimentProposal):
        with SessionFactory.get_session() as session:
            ExperimentRepository(session).save(proposal)

    def store_lesson(self, lesson: Lesson):
        with SessionFactory.get_session() as session:
            LessonRepository(session).save(lesson)

    def get_recent_episodes(self, limit: int = 50) -> list[dict]:
        with SessionFactory.get_session() as session:
            return [dict(row) for row in EpisodeRepository(session).latest(limit)]

    def get_beliefs(self) -> list[dict]:
        with SessionFactory.get_session() as session:
            return BeliefRepository(session).all()
