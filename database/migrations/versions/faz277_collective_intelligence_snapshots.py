"""Cognitive Core 10.0 — Collective Intelligence (Condorcet'in Jüri Teoremi) haftalık anlık görüntüsü.

analytics/collective_intelligence.py::compute_expected_majority_accuracy()
(Faz 971-1000) yazılmış ve testliydi ama hiçbir üretim kodu onu
çağırmıyordu — 10 ajanlı council'in toplamının GERÇEKTEN en iyi tekil
ajandan daha isabetli olup olmadığı hiç doğrulanmamıştı. Causal
Inference'tan sonraki, council'i etkilemeyen Grup B adayı.

Revision ID: faz277
Revises: faz276
Create Date: 2026-08-18
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz277"
down_revision = "faz276"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collective_intelligence_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_collective_intelligence_snapshots_created_at", "collective_intelligence_snapshots", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_collective_intelligence_snapshots_created_at", table_name="collective_intelligence_snapshots")
    op.drop_table("collective_intelligence_snapshots")
