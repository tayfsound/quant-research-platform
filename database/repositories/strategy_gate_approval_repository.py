"""Strategy Gate Approval repository — Faz 366. weight_approval_
repository.py ile AYNI desen (propose→pending→approve/reject, dedup,
auto-reject-stale).

Faz 366-devam — kullanıcı bulgusu: status="approved" yanıltıcı okunuyordu
("onaylı strateji" = "kazandıran strateji" gibi algılanabiliyordu, oysa
burada onaylanan şey stratejinin İYİLİĞİ değil, o rejimde ENGELLENMESİ).
Statü değerleri "blocked"/"dismissed"e çevrildi — hiçbir okunuşta ters
anlama gelmiyor. approve()/reject() API fiil olarak kalıyor (insanın
attığı AKSİYON hâlâ "onayla/reddet"), ama SONUÇ durumu artık net."""
from datetime import datetime, timedelta

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from contracts.strategy_gate_approval import StrategyGateApproval
from database.base import Base


class StrategyGateApprovalModel(Base):
    __tablename__ = "strategy_gate_approvals"
    id = Column(UUID(as_uuid=True), primary_key=True)
    timestamp = Column(DateTime, nullable=False)
    strategy = Column(String(64), nullable=False)
    market_regime = Column(String(64), nullable=False)
    sample_size = Column(Integer, nullable=False)
    win_rate = Column(Float, nullable=False)
    rest_win_rate = Column(Float, nullable=False)
    delta_vs_rest = Column(Float, nullable=False)
    p_value = Column(Float, nullable=False)
    replicated_out_of_sample = Column(Boolean, nullable=True)
    status = Column(String(16), default="pending")  # pending | blocked | dismissed
    approved_by = Column(String(64), default="")
    expires_at = Column(DateTime, nullable=True)
    decided_at = Column(DateTime, nullable=True)


class StrategyGateApprovalRepository:
    def __init__(self, session):
        self.session = session

    def save(self, approval: StrategyGateApproval) -> None:
        row = StrategyGateApprovalModel(
            id=approval.id,
            timestamp=approval.timestamp,
            strategy=approval.strategy,
            market_regime=approval.market_regime,
            sample_size=approval.sample_size,
            win_rate=approval.win_rate,
            rest_win_rate=approval.rest_win_rate,
            delta_vs_rest=approval.delta_vs_rest,
            p_value=approval.p_value,
            replicated_out_of_sample=approval.replicated_out_of_sample,
            status=approval.status,
            approved_by=approval.approved_by,
            expires_at=approval.expires_at,
            decided_at=approval.decided_at,
        )
        self.session.add(row)
        self.session.commit()

    def get_pending(self, limit: int = 10):
        return (
            self.session.query(StrategyGateApprovalModel)
            .filter_by(status="pending")
            .order_by(StrategyGateApprovalModel.timestamp.desc())
            .limit(limit)
            .all()
        )

    def has_pending_or_blocked(self, strategy: str, market_regime: str) -> bool:
        """weight_approval_repository.py::has_pending ile AYNI gerekçe
        (Faz 229) — zaten bekleyen ya da zaten engellenmiş bir aday
        varsa aynı (strateji, rejim) çifti için yenisi eklenmiyor,
        kuyruk şişmiyor."""
        return (
            self.session.query(StrategyGateApprovalModel)
            .filter(
                StrategyGateApprovalModel.strategy == strategy,
                StrategyGateApprovalModel.market_regime == market_regime,
                StrategyGateApprovalModel.status.in_(("pending", "blocked")),
            )
            .first()
            is not None
        )

    def approve(self, approval_id: str, approved_by: str = "human") -> None:
        """İnsanın "bu (strateji, rejim) engellensin" AKSİYONU — sonuç
        durumu "blocked" (stratejinin kendisi "onaylı" değil, engelleme
        kararı onaylı)."""
        self.session.query(StrategyGateApprovalModel).filter_by(id=approval_id).update(
            {"status": "blocked", "approved_by": approved_by, "decided_at": datetime.now()}
        )
        self.session.commit()

        from uuid import UUID as PyUUID

        from database.repositories.event_log_repository import EventLogRepository

        EventLogRepository(self.session).record(
            event_type="strategy_gate_blocked",
            entity_type="strategy_gate_approval",
            entity_id=PyUUID(str(approval_id)),
            payload={"approved_by": approved_by},
        )

    def auto_reject_stale(self, max_age_seconds: float = 24 * 3600) -> int:
        cutoff = datetime.now() - timedelta(seconds=max_age_seconds)
        rows = (
            self.session.query(StrategyGateApprovalModel)
            .filter(StrategyGateApprovalModel.status == "pending", StrategyGateApprovalModel.timestamp < cutoff)
            .all()
        )
        for row in rows:
            row.status = "dismissed"
            row.decided_at = datetime.now()
        self.session.commit()
        return len(rows)

    def list_blocked_pairs(self) -> set[tuple[str, str]]:
        """Şu an gerçekten canlı gate'te uygulanması gereken (strateji,
        rejim) çiftleri — decision_recorder.py bunu okuyor. blocked
        DIŞINDAKİ (pending/dismissed) hiçbir satır gate'i etkilemez."""
        rows = (
            self.session.query(StrategyGateApprovalModel.strategy, StrategyGateApprovalModel.market_regime)
            .filter_by(status="blocked")
            .all()
        )
        return {(r.strategy, r.market_regime) for r in rows}
