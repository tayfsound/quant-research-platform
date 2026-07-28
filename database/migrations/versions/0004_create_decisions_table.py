"""Create decisions table.

Revision ID: 0004
Revises: 0003
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("size", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("agent_contributions", postgresql.JSONB(), nullable=True),
        sa.Column("weight_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("belief_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("pnl", sa.Float(), nullable=True),
    )
    op.create_index("ix_decisions_symbol", "decisions", ["symbol"])
    op.create_index("ix_decisions_timestamp", "decisions", ["timestamp"])


def downgrade() -> None:
    op.drop_index("ix_decisions_timestamp", table_name="decisions")
    op.drop_index("ix_decisions_symbol", table_name="decisions")
    op.drop_table("decisions")
