"""Cognitive Core 3.0 — Self-Model haftalık öz-güvenilirlik anlık görüntüsü.

analytics/self_model.py::compute_self_reliability_snapshot() zaten yazılmış
ve testliydi (Faz 769-800) ama hiçbir üretim kodu onu çağırmıyordu — Grup B
(council'i etkilemeyen, gözlemsel) roadmap modüllerinden ikinci canlıya
alınan (ECE'den sonra). calibration_reports/feature_ic_reports ile AYNI
desen: periyodik (haftalık) anlık görüntüleri saklar.

Revision ID: faz275
Revises: faz274
Create Date: 2026-08-18
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz275"
down_revision = "faz274"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "self_model_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_self_model_snapshots_created_at", "self_model_snapshots", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_self_model_snapshots_created_at", table_name="self_model_snapshots")
    op.drop_table("self_model_snapshots")
