"""Cognitive Core 2.0 / M4 — Direction Prediction v2 (Brier Score) haftalık anlık görüntüsü.

analytics/direction_prediction_v2.py::compute_brier_score() (Faz
519-543) yazılmış ve testliydi ama hiçbir üretim kodu onu çağırmıyordu.
Kullanıcı onayıyla (2026-08-19) 4 Grup B modülü birlikte canlıya
alınıyor.

Revision ID: faz287
Revises: faz286
Create Date: 2026-08-19
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz287"
down_revision = "faz286"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "direction_prediction_v2_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
    )
    op.create_index(
        "ix_direction_prediction_v2_snapshots_created_at",
        "direction_prediction_v2_snapshots", ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_direction_prediction_v2_snapshots_created_at",
        table_name="direction_prediction_v2_snapshots",
    )
    op.drop_table("direction_prediction_v2_snapshots")
