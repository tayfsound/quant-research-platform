"""Cognitive Core 2.0 / M10 — Meta-Learning Effectiveness haftalık anlık görüntüsü.

analytics/meta_learning_effectiveness.py::compute_meta_learning_trend()
(Faz 744-768) yazılmış ve testliydi ama hiçbir üretim kodu onu
çağırmıyordu — meta_optimizer/agent_tuner.py'nin (CMA-ES) turlarının
GERÇEKTEN zamanla iyileşip iyileşmediği hiç ölçülmüyordu. Kullanıcı
onayıyla (2026-08-19) 4 Grup B modülü birlikte canlıya alınıyor —
council'i etkilemeyen, saf ölçüm/rapor katmanları.

Revision ID: faz285
Revises: faz284
Create Date: 2026-08-19
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz285"
down_revision = "faz284"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "meta_learning_effectiveness_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
    )
    op.create_index(
        "ix_meta_learning_effectiveness_snapshots_created_at",
        "meta_learning_effectiveness_snapshots", ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_meta_learning_effectiveness_snapshots_created_at",
        table_name="meta_learning_effectiveness_snapshots",
    )
    op.drop_table("meta_learning_effectiveness_snapshots")
