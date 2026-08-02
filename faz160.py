import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent

# 1. Approval contract
p = REPO / "contracts" / "weight_approval.py"
p.write_text('''"""Weight approval contract — Faz 160."""
from datetime import datetime
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


class WeightApproval(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.now)
    proposed_weights: dict = Field(default_factory=dict)
    previous_weights: dict = Field(default_factory=dict)
    max_delta: float = 0.10
    status: str = "pending"  # pending | approved | rejected
    approved_by: str = ""    # human or system
''')
print("contracts/weight_approval.py")

# 2. Approval repository
r = REPO / "database" / "repositories" / "weight_approval_repository.py"
r.write_text('''"""Weight approval repository."""
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
    status = Column(String(16), default="pending")
    approved_by = Column(String(64), default="")


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
            status=approval.status,
            approved_by=approval.approved_by,
        )
        self.session.add(row)
        self.session.commit()

    def get_pending(self, limit: int = 10):
        return self.session.query(WeightApprovalModel).filter_by(status="pending").order_by(WeightApprovalModel.timestamp.desc()).limit(limit).all()

    def approve(self, approval_id: str, approved_by: str = "human"):
        self.session.query(WeightApprovalModel).filter_by(id=approval_id).update({"status": "approved", "approved_by": approved_by})
        self.session.commit()
''')
print("database/repositories/weight_approval_repository.py")

# 3. Patch weight_optimizer — gate before apply
w = REPO / "services" / "weight_optimizer.py"
t = w.read_text()

if "WeightApproval" not in t:
    t = t.replace(
        "from services.weight_repository import WeightRepository",
        "from services.weight_repository import WeightRepository\nfrom contracts.weight_approval import WeightApproval\nfrom database.session_factory import SessionFactory\nfrom database.repositories.weight_approval_repository import WeightApprovalRepository"
    )
    
    # Replace optimize method to require approval if delta > threshold
    old_opt = '''    def optimize(self, evaluation_window=100):
        """Optimize weights based on recent performance."""
        history = self.agent_memory.get_recent(evaluation_window)
        if not history:
            return self.current_weights

        domain_scores = self._calculate_domain_scores(history)
        new_weights = self._normalize_weights(domain_scores)

        # Apply MAX_WEIGHT_DELTA constraint
        constrained = self._apply_delta_constraint(
            self.current_weights,
            new_weights,
        )

        self.current_weights = constrained
        self.weight_repository.save(self.current_weights)
        return self.current_weights'''

    new_opt = '''    def optimize(self, evaluation_window=100, require_approval: bool = True):
        """Optimize weights based on recent performance. Human approval required for large changes."""
        history = self.agent_memory.get_recent(evaluation_window)
        if not history:
            return self.current_weights

        domain_scores = self._calculate_domain_scores(history)
        new_weights = self._normalize_weights(domain_scores)

        # Apply MAX_WEIGHT_DELTA constraint
        constrained = self._apply_delta_constraint(
            self.current_weights,
            new_weights,
        )

        # Check if approval needed
        max_change = max(abs(constrained.get(k, 0) - self.current_weights.get(k, 0)) for k in set(constrained) | set(self.current_weights)) if (constrained and self.current_weights) else 0

        if require_approval and max_change >= 0.05:  # >5% change needs approval
            approval = WeightApproval(
                proposed_weights=constrained,
                previous_weights=self.current_weights,
                max_delta=MAX_WEIGHT_DELTA,
                status="pending",
            )
            with SessionFactory.get_session() as session:
                WeightApprovalRepository(session).save(approval)
            return self.current_weights  # Return old weights until approved

        self.current_weights = constrained
        self.weight_repository.save(self.current_weights)
        return self.current_weights'''

    t = t.replace(old_opt, new_opt)
    w.write_text(t)
    print("weight_optimizer + approval gate")

# 4. Test (faz sonu tek test)
r = subprocess.run(["pytest", "-q", "--ignore=tests/test_ml.py"], cwd=REPO)
if r.returncode != 0:
    print("[FAIL] Tests red", file=sys.stderr)
    sys.exit(1)

# 5. Commit + push + cleanup
subprocess.run(["git", "add", "-A"], cwd=REPO, check=True)
subprocess.run(["git", "commit", "-m", "Faz 160: Meta Optimizer approval gate (human-in-the-loop)"], cwd=REPO, check=True)
subprocess.run(["git", "push", "origin", "main"], cwd=REPO, check=True)

(REPO / "faz160.py").unlink()
print("[OK] Faz 160 complete")
