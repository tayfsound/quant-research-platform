"""Faz 401 — Market State Cluster Engine periyodik anlık görüntüsü.

Market State / Direction Katmanı büyük mimari projesinin (bkz.
/Users/emreturkes/.claude/plans/velvety-whistling-parasol.md) Faz 1'i.
historical_analog_snapshots ile AYNI desende (id/created_at/result JSONB)
5 dakikalık bir anlık görüntü saklıyor.

Revision ID: faz401
Revises: faz394
Create Date: 2026-09-01
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz401"
down_revision = "faz394"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_state_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_market_state_snapshots_created_at", "market_state_snapshots", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_market_state_snapshots_created_at", table_name="market_state_snapshots")
    op.drop_table("market_state_snapshots")
