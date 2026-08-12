"""Faz 239-241: create agent_tuning_approvals table.

Online Meta-Learning (CMA-ES ile ajan skorlama katsayılarının gerçek
geçmiş verilerle ayarlanması) — WeightApproval (Faz 160-165) ile AYNI
insan-onay-kapısı deseni, ama ağırlıklar yerine bir ajanın KENDİ iç
skorlama katsayıları (bkz. agents/technical_agent.py::
TechnicalAgentCoefficients) için. Yeni θ asla walk-forward out-of-sample
Sharpe'ı geçmeden VE insan onayı almadan canlıya uygulanmıyor.

Revision ID: faz239
Revises: faz268b
Create Date: 2026-08-12
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz239"
down_revision = "faz268b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_tuning_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("proposed_coefficients", postgresql.JSON(), nullable=True),
        sa.Column("previous_coefficients", postgresql.JSON(), nullable=True),
        sa.Column("in_sample_sharpe", sa.Float(), nullable=True),
        sa.Column("mean_oos_sharpe_tuned", sa.Float(), nullable=True),
        sa.Column("mean_oos_sharpe_baseline", sa.Float(), nullable=True),
        sa.Column("sharpe_improvement", sa.Float(), nullable=True),
        sa.Column("sample_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=True),
        sa.Column("approved_by", sa.String(64), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("agent_tuning_approvals")
