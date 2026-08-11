"""Weight approval repository."""
from datetime import datetime, timedelta

from sqlalchemy import Column, String, DateTime, Float, JSON
from sqlalchemy.dialects.postgresql import UUID
from database.base import Base
from contracts.weight_approval import WeightApproval


class WeightApprovalModel(Base):
    __tablename__ = "weight_approvals"
    id = Column(UUID(as_uuid=True), primary_key=True)
    timestamp = Column(DateTime, nullable=False)
    proposed_weights = Column(JSON, default=dict)
    previous_weights = Column(JSON, default=dict)
    max_delta = Column(Float, default=0.10)
    regime = Column(String(64), nullable=True)
    status = Column(String(16), default="pending")
    approved_by = Column(String(64), default="")
    expires_at = Column(DateTime, nullable=True)
    decided_at = Column(DateTime, nullable=True)


class WeightApprovalRepository:
    def __init__(self, session):
        self.session = session

    def save(self, approval: WeightApproval) -> None:
        row = WeightApprovalModel(
            id=approval.id,
            timestamp=approval.timestamp,
            proposed_weights=approval.proposed_weights,
            previous_weights=approval.previous_weights,
            max_delta=approval.max_delta,
            regime=approval.regime,
            status=approval.status,
            approved_by=approval.approved_by,
            expires_at=approval.expires_at,
            decided_at=approval.decided_at,
        )
        self.session.add(row)
        self.session.commit()

    def get_pending(self, limit: int = 10):
        return self.session.query(WeightApprovalModel).filter_by(status="pending").order_by(WeightApprovalModel.timestamp.desc()).limit(limit).all()

    def has_pending(self, regime: str | None = None) -> bool:
        """Faz 229: kritik bulgu — WeightOptimizer.optimize()/propose_weights()
        her büyük ağırlık değişikliğinde KOŞULSUZCA yeni bir onay satırı
        oluşturuyordu, mevcut bekleyen bir onay olup olmadığını hiç kontrol
        etmeden. Gerçek üretimde bu, her gerçek trading cycle'da (optimize())
        ve her gerçek pozisyon kapanışında (propose_weights()) tetiklenip
        canlı DB'de 7000'den fazla neredeyse aynı satır biriktirdi — insan
        gözden geçiremeyeceği bir kuyruk, ve gerçek ağırlıklar saatlerce
        güncellenmeden donuk kaldı (her iki metod da onaylanana kadar ESKİ
        ağırlığı döndürüyor). Artık yeni bir onay oluşturmadan önce burası
        kontrol ediliyor — zaten bekleyen bir onay varsa yenisi eklenmiyor.

        Faz 268b — Regime-Aware Learning: regime parametresi olmadan bu
        kontrol GLOBAL çalışırdı — bir rejimin bekleyen onayı, TAMAMEN
        FARKLI bir rejimin yeni önerisini de bloke ederdi (iki rejim aynı
        anda pending kalamaz gibi yanlış bir davranış). Artık her rejim
        kendi bekleyen onayına göre kontrol ediliyor."""
        return (
            self.session.query(WeightApprovalModel)
            .filter_by(status="pending", regime=regime)
            .first()
            is not None
        )

    def approve(self, approval_id: str, approved_by: str = "human"):
        self.session.query(WeightApprovalModel).filter_by(id=approval_id).update(
            {"status": "approved", "approved_by": approved_by, "decided_at": datetime.now()}
        )
        self.session.commit()

    def auto_reject_stale(self, max_age_seconds: float = 3600) -> int:
        """Reject pending approvals older than max_age_seconds. Returns rejected count."""
        cutoff = datetime.now() - timedelta(seconds=max_age_seconds)
        rows = (
            self.session.query(WeightApprovalModel)
            .filter(WeightApprovalModel.status == "pending", WeightApprovalModel.timestamp < cutoff)
            .all()
        )
        for row in rows:
            row.status = "rejected"
            row.decided_at = datetime.now()
        self.session.commit()
        return len(rows)

    def approval_latency_metrics(self) -> dict:
        """Latency (seconds) between creation and approval, for approved rows."""
        rows = (
            self.session.query(WeightApprovalModel)
            .filter(WeightApprovalModel.status == "approved", WeightApprovalModel.decided_at.isnot(None))
            .all()
        )
        latencies = sorted((r.decided_at - r.timestamp).total_seconds() for r in rows)
        if not latencies:
            return {"avg_seconds": 0.0, "max_seconds": 0.0, "p95_seconds": 0.0}
        p95_idx = min(len(latencies) - 1, round(0.95 * (len(latencies) - 1)))
        return {
            "avg_seconds": sum(latencies) / len(latencies),
            "max_seconds": latencies[-1],
            "p95_seconds": latencies[p95_idx],
        }
