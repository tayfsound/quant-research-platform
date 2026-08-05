"""Faz 196: onchain_snapshots — gerçek zincir-üstü metriklerin zaman
serisi. Sadece 24 saatlik delta hesaplayabilmek için (örn. stablecoin_
mint_24h) gereken minimum tarihçe; "kolay/dürüst" metrikler dışında bir
şey saklamıyor.

Revision ID: faz196
Revises: faz192
Create Date: 2026-08-06
"""
import sqlalchemy as sa
from alembic import op

revision = "faz196"
down_revision = "faz192"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "onchain_snapshots",
        sa.Column("metric", sa.String(64), nullable=False),
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("metric", "time"),
    )
    op.execute("SELECT create_hypertable('onchain_snapshots', 'time', if_not_exists => TRUE);")
    op.create_index("ix_onchain_snapshots_metric_time", "onchain_snapshots", ["metric", "time"])


def downgrade() -> None:
    op.drop_index("ix_onchain_snapshots_metric_time", table_name="onchain_snapshots")
    op.drop_table("onchain_snapshots")
