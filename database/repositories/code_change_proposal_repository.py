"""Code Change Proposal repository — Faz 270."""
from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID

from contracts.code_change_proposal import CodeChangeProposal
from database.base import Base


class CodeChangeProposalModel(Base):
    __tablename__ = "code_change_proposals"
    id = Column(UUID(as_uuid=True), primary_key=True)
    created_at = Column(DateTime, nullable=False)
    title = Column(String(200), nullable=False)
    file_path = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)
    diff = Column(Text, nullable=False)
    rationale = Column(Text, nullable=False)
    status = Column(String(16), default="pending")
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by = Column(String(100), nullable=True)


class CodeChangeProposalRepository:
    def __init__(self, session):
        self.session = session

    def save(self, proposal: CodeChangeProposal) -> None:
        row = CodeChangeProposalModel(
            id=proposal.id,
            created_at=proposal.created_at,
            title=proposal.title,
            file_path=proposal.file_path,
            description=proposal.description,
            diff=proposal.diff,
            rationale=proposal.rationale,
            status=proposal.status,
            reviewed_at=proposal.reviewed_at,
            reviewed_by=proposal.reviewed_by,
        )
        self.session.add(row)
        self.session.commit()

    def get_pending(self, limit: int = 50) -> list[dict]:
        rows = (
            self.session.query(CodeChangeProposalModel)
            .filter_by(status="pending")
            .order_by(CodeChangeProposalModel.created_at.desc())
            .limit(limit)
            .all()
        )
        return [self._to_dict(r) for r in rows]

    def get_all(self, limit: int = 50) -> list[dict]:
        rows = (
            self.session.query(CodeChangeProposalModel)
            .order_by(CodeChangeProposalModel.created_at.desc())
            .limit(limit)
            .all()
        )
        return [self._to_dict(r) for r in rows]

    def get_by_id(self, proposal_id: str) -> dict | None:
        row = self.session.query(CodeChangeProposalModel).filter_by(id=proposal_id).first()
        return self._to_dict(row) if row else None

    def decide(self, proposal_id: str, status: str, reviewed_by: str = "human") -> bool:
        """status: "approved" | "rejected". Sadece durum değişir — hiçbir
        dosya buradan diske yazılmaz (bkz. migration docstring'i)."""
        result = self.session.query(CodeChangeProposalModel).filter_by(
            id=proposal_id, status="pending",
        ).update({
            "status": status,
            "reviewed_at": datetime.now(),
            "reviewed_by": reviewed_by,
        })
        self.session.commit()
        return result > 0

    @staticmethod
    def _to_dict(row: CodeChangeProposalModel) -> dict:
        return {
            "id": str(row.id),
            "created_at": row.created_at.isoformat(),
            "title": row.title,
            "file_path": row.file_path,
            "description": row.description,
            "diff": row.diff,
            "rationale": row.rationale,
            "status": row.status,
            "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
            "reviewed_by": row.reviewed_by,
        }
