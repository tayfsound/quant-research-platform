"""Episode repository — CAST ile embedding."""
import json
from sqlalchemy import text
from contracts.memory import Episode

class EpisodeRepository:
    def __init__(self, session):
        self.session = session

    def save(self, episode: Episode, embedding: list[float] | None = None):
        data = episode.model_dump(mode="json")
        for field in ("observation", "outcome"):
            if isinstance(data.get(field), dict):
                data[field] = json.dumps(data[field])
        data["id"] = str(data["id"])
        if data.get("cycle_id"):
            data["cycle_id"] = str(data["cycle_id"])
        # Embedding — CAST kullan
        if embedding:
            data["embedding"] = "[" + ",".join(str(v) for v in embedding) + "]"
        else:
            data["embedding"] = None

        self.session.execute(
            text("""INSERT INTO episodes (id, cycle_id, symbol, observation, binding_expression, decision, outcome, lesson, embedding)
               VALUES (:id, :cycle_id, :symbol, :observation, :binding_expression, :decision, :outcome, :lesson, CAST(:embedding AS vector))"""),
            data,
        )

        self.session.commit()

        return episode

    def latest(self, limit: int = 20):
        result = self.session.execute(
            text("SELECT * FROM episodes ORDER BY created_at DESC LIMIT :limit"),
            {"limit": limit},
        )
        return result.mappings().all()
