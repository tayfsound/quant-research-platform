"""Risk Limit repository — gap #15: DB-backed, insan-onaylı (ADMIN) risk limitleri.

`contracts/contexts/risk.py::RiskLimitEntry` (value + hash + verify(secret))
zaten `RiskEngine`'in beklediği gerçek arayüz — bu repository onu kalıcı
kılıyor. Class 2: sadece save/get_active, update/delete yok (weight_approvals
ve experiment_registry ile aynı desen); yeni bir limit set etmek eskisini
silmez, sadece daha yeni bir created_at ile "aktif" olanı değiştirir.
"""
from uuid import uuid4

from sqlalchemy import Column, DateTime, Float, String
from sqlalchemy.dialects.postgresql import UUID

from contracts.contexts.risk import RiskLimitEntry
from database.base import Base


class RiskLimitModel(Base):
    __tablename__ = "risk_limits"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    scope = Column(String(64), nullable=False, default="global")
    limit_type = Column(String(32), nullable=False)
    value = Column(Float, nullable=False)
    hash = Column(String(64), nullable=False, default="")
    created_by = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False)


class RiskLimitRepository:
    def __init__(self, session):
        self.session = session

    def save(self, row: RiskLimitModel) -> None:
        self.session.add(row)
        self.session.commit()

    def get_active(self, scope: str, limit_type: str) -> RiskLimitModel | None:
        return (
            self.session.query(RiskLimitModel)
            .filter_by(scope=scope, limit_type=limit_type)
            .order_by(RiskLimitModel.created_at.desc())
            .first()
        )

    def list_active(self, scope: str = "global") -> list[RiskLimitModel]:
        """Her limit_type için en güncel satırı döner (o an gerçekten geçerli olan set)."""
        rows = (
            self.session.query(RiskLimitModel)
            .filter_by(scope=scope)
            .order_by(RiskLimitModel.created_at.desc())
            .all()
        )
        latest_by_type: dict[str, RiskLimitModel] = {}
        for row in rows:
            latest_by_type.setdefault(row.limit_type, row)
        return list(latest_by_type.values())


def to_entry(row: RiskLimitModel | None) -> RiskLimitEntry | None:
    if row is None:
        return None
    return RiskLimitEntry(value=row.value, hash=row.hash)


def load_active_limits(scope: str = "global") -> dict[str, RiskLimitEntry]:
    """Single shared loader for ctx.risk.limits — both `/cognitive/run` and
    `CognitiveOrchestrator.run_cycle()` call this instead of each opening
    their own ad-hoc query (that duplication is exactly how gap #15 stayed
    half-fixed the first time: fixing one production entrypoint but not the
    other)."""
    from database.session_factory import SessionFactory

    with SessionFactory.get_session() as session:
        rows = RiskLimitRepository(session).list_active(scope=scope)
        return {row.limit_type: to_entry(row) for row in rows}
