"""Faz 369: Agent Interaction (pairwise ablation) haftalık rapor geçmişi.

GPT dış rapor önerisi ("Agent Interaction & Incremental Information
Layer"), kullanıcı kararıyla ilk iş sırası olarak seçildi. agent_
ablation_snapshots (Faz 296) ile AYNI generic desen — sadece ölçüm/kayıt,
karar hattına bağlanmıyor.

Revision ID: faz369
Revises: faz368
Create Date: 2026-08-29
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz369"
down_revision = "faz368"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_pairwise_ablation_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
    )
    op.create_index(
        "ix_agent_pairwise_ablation_snapshots_created_at",
        "agent_pairwise_ablation_snapshots", ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_pairwise_ablation_snapshots_created_at", table_name="agent_pairwise_ablation_snapshots")
    op.drop_table("agent_pairwise_ablation_snapshots")
