"""Cognitive Core 5.0-6.0 — Market World Model haftalık anlık görüntüsü.

analytics/market_world_model.py::compute_block_bootstrap_paths() (Faz
901-940, Moving Block Bootstrap — Künsch 1989) yazılmış ve testliydi ama
hiçbir üretim kodu onu çağırmıyordu. Kullanıcı onayıyla (2026-08-19) 4
Grup B modülü birlikte canlıya alınıyor.

Revision ID: faz286
Revises: faz285
Create Date: 2026-08-19
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz286"
down_revision = "faz285"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_world_model_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
    )
    op.create_index(
        "ix_market_world_model_snapshots_created_at",
        "market_world_model_snapshots", ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_market_world_model_snapshots_created_at",
        table_name="market_world_model_snapshots",
    )
    op.drop_table("market_world_model_snapshots")
