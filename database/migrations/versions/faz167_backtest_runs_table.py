"""Faz 167 / Sprint 6: create backtest_runs table (Class 2, never deleted).

Revision ID: faz167
Revises: faz166
Create Date: 2026-08-04
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz167"
down_revision = "faz166"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backtest_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("symbols", postgresql.JSON(), nullable=False),
        sa.Column("git_sha", sa.String(40), nullable=False),
        sa.Column("weight_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("fee", sa.Float(), nullable=False),
        sa.Column("lookback", sa.Integer(), nullable=False),
        sa.Column("num_bars", sa.Integer(), nullable=False),
        sa.Column("total_pnl", sa.Float(), nullable=False),
        sa.Column("per_symbol_pnl", postgresql.JSON(), nullable=False),
        sa.Column("metrics", postgresql.JSON(), nullable=False),
        sa.Column("equity_curve", postgresql.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("backtest_runs")
