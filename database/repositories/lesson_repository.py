"""Lesson repository — commit yok."""
from sqlalchemy import text

from contracts.evaluation import Lesson


class LessonRepository:
    def __init__(self, session):
        self.session = session

    def save(self, lesson: Lesson):
        data = {
            "id": str(lesson.id),
            "episode_id": str(lesson.episode_id) if lesson.episode_id else None,
            "lesson_text": lesson.lesson_text,
            "category": lesson.category,
            "severity": lesson.severity,
        }
        self.session.execute(
            text("""INSERT INTO lessons (id, episode_id, lesson_text, category, severity)
               VALUES (:id, :episode_id, :lesson_text, :category, :severity)"""),
            data,
        )

    def latest(self, limit: int = 20) -> list[dict]:
        result = self.session.execute(
            text("SELECT * FROM lessons ORDER BY created_at DESC LIMIT :limit"),
            {"limit": limit},
        )
        return [dict(row) for row in result.mappings().all()]
