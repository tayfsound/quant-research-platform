"""Observation repository — commit yok, cycle_id opsiyonel."""
import json
from datetime import UTC, datetime

from sqlalchemy import text

from contracts.observation import Observation


class ObservationRepository:
    def __init__(self, session):
        self.session = session

    def save(self, obs: Observation):
        data = obs.model_dump()
        data["id"] = str(data["id"])
        if hasattr(data.get("type"), "value"):
            data["observation_type"] = data["type"].value
        else:
            data["observation_type"] = str(data.get("type", ""))
        data.pop("type", None)
        # cycle_id yoksa ekleme
        if "cycle_id" not in data or data["cycle_id"] is None:
            data["cycle_id"] = None
        else:
            data["cycle_id"] = str(data["cycle_id"])
        if isinstance(data.get("data"), dict):
            data["data"] = json.dumps(data["data"])
        # Aynı gerçek bulgu: created_at hiç set edilmiyordu, migration'da
        # nullable=False + server_default yok — sadece gerçek dev DB'nin
        # şema kayması (elle eklenmiş DEFAULT now()) yüzünden çalışıyordu.
        data["created_at"] = datetime.now(UTC)

        self.session.execute(
            text("""INSERT INTO observations (id, cycle_id, symbol, observation_type, data, created_at)
               VALUES (:id, :cycle_id, :symbol, :observation_type, :data, :created_at)"""),
            data,
        )

    def latest(self, limit: int = 20):
        result = self.session.execute(
            text("SELECT * FROM observations ORDER BY created_at DESC LIMIT :limit"),
            {"limit": limit},
        )
        return result.mappings().all()
