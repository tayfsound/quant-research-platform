"""Faz 394 — Historical Analog Engine (FIL Faz D) haftalık anlık görüntüsü.

analytics/historical_analog_engine.py (bugün, aynı oturumda kuruldu)
canlı çağrıldığında pahalı (1831+ kapanmış karar taraması) — bu tablo
causal_inference_snapshots/agent_combination_reliability_snapshots ile
AYNI desende haftalık bir anlık görüntü saklıyor.

Revision ID: faz394
Revises: faz375
Create Date: 2026-09-01
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz394"
down_revision = "faz375"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "historical_analog_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_historical_analog_snapshots_created_at", "historical_analog_snapshots", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_historical_analog_snapshots_created_at", table_name="historical_analog_snapshots")
    op.drop_table("historical_analog_snapshots")
