"""Faz 269 (Cognitive Core 2.0 / M1): system_events — sistemdeki önemli
olayların TEK, birleşik, append-only zaman çizelgesi. Mevcut tabloların
(app_settings, weight_approvals, decisions) YERİNE geçmiyor, onları
TEKRARLAMADAN üstlerine bir olay günlüğü ekliyor — payload içinde ilgili
tablonun kendi id'sine referans veriliyor."""
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from database.base import Base


class SystemEventModel(Base):
    __tablename__ = "system_events"
    id = Column(PGUUID(as_uuid=True), primary_key=True)
    event_type = Column(String(64), nullable=False)
    entity_type = Column(String(64), nullable=True)
    entity_id = Column(PGUUID(as_uuid=True), nullable=True)
    payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)


class EventLogRepository:
    def __init__(self, session):
        self.session = session

    def record(
        self,
        event_type: str,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        payload: dict | None = None,
    ) -> None:
        """Fail-closed DEĞİL, kasıtlı olarak sessiz-başarısız: bir olayı
        kaydedememek (ör. tablo henüz yoksa eski bir migration'da) çağıran
        tarafın GERÇEK işini (ör. kill switch'i tetiklemek) engellememeli
        — RiskEngine._trip_kill_switch()'in kendi try/except'iyle AYNI
        felsefe. Olay günlüğü bir denetim katmanı, tek gerçek kaynak
        değil."""
        try:
            row = SystemEventModel(
                id=uuid4(),
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                payload=payload or {},
                created_at=datetime.now(UTC),
            )
            self.session.add(row)
            self.session.commit()
        except Exception:
            import structlog

            structlog.get_logger().warning("system_event_record_failed", event_type=event_type)

    def list_events(
        self,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        query = self.session.query(SystemEventModel)
        if event_type is not None:
            query = query.filter_by(event_type=event_type)
        rows = query.order_by(SystemEventModel.created_at.desc()).limit(limit).all()
        return [
            {
                "id": str(r.id),
                "event_type": r.event_type,
                "entity_type": r.entity_type,
                "entity_id": str(r.entity_id) if r.entity_id else None,
                "payload": r.payload,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
