"""Faz 331 — Agent Combination Reliability haftalık anlık görüntüsü.

Opportunity Quality (Faz 569-593) KAÇ ajanın anlaştığını win_rate ile
ilişkilendiriyor — bu tablo HANGİ ajan İKİLİLERİNİN birlikte anlaştığını
ilişkilendiren periyodik anlık görüntüleri saklıyor, Causal Inference/
Agent Ablation ile AYNI desen.

Revision ID: faz331
Revises: faz319
Create Date: 2026-08-21
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz331"
down_revision = "faz319"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_combination_reliability_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
    )
    op.create_index(
        "ix_agent_combination_reliability_snapshots_created_at",
        "agent_combination_reliability_snapshots",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_combination_reliability_snapshots_created_at",
        table_name="agent_combination_reliability_snapshots",
    )
    op.drop_table("agent_combination_reliability_snapshots")
