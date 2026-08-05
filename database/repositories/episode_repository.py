"""Episode repository — CAST ile embedding."""
import json
from datetime import UTC, datetime

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
        # Gerçek bulgu: created_at hiç set edilmiyordu — migration'da
        # nullable=False ve server_default yok, sadece gerçek dev DB'de
        # şema kayması (elle eklenmiş DEFAULT now()) yüzünden çalışıyor
        # gibi görünüyordu. Ayrı, migrations-only bir test DB'sinde
        # NotNullViolation ile patlıyordu — kod tarafında açıkça set ediliyor.
        data["created_at"] = datetime.now(UTC)

        self.session.execute(
            text("""INSERT INTO episodes (id, cycle_id, symbol, observation, binding_expression, decision, outcome, lesson, embedding, created_at)
               VALUES (:id, :cycle_id, :symbol, :observation, :binding_expression, :decision, :outcome, :lesson, CAST(:embedding AS vector), :created_at)"""),
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
