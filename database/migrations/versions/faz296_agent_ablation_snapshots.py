"""Faz 296 — Agent Ablation haftalık anlık görüntüsü.

analytics/agent_ablation.py::compute_leave_one_out_impact() (kullanıcı
isteği, 2026-08-19: mevcut auto-bench SADECE davranışsal/geriye dönük
doğruluk ölçüyordu, "bu ajanın oyu olmasaydı gerçekleşen kararlar farklı
olur muydu" sorusuna hiç cevap vermiyordu) gerçek kapanmış kararların
saklanmış agent_contributions'ından GERÇEK bir leave-one-out
rekonstrüksiyon yapıyor.

Revision ID: faz296
Revises: faz288
Create Date: 2026-08-19
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz296"
down_revision = "faz288"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_ablation_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
    )
    op.create_index(
        "ix_agent_ablation_snapshots_created_at",
        "agent_ablation_snapshots", ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_ablation_snapshots_created_at",
        table_name="agent_ablation_snapshots",
    )
    op.drop_table("agent_ablation_snapshots")
