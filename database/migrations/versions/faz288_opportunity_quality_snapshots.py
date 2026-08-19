"""Cognitive Core 2.0 — Opportunity Quality / Meta-Labeling haftalık anlık görüntüsü.

analytics/opportunity_quality.py::compute_agent_agreement()/
compute_opportunity_quality_by_agreement() (Faz 569-593, de Prado
meta-labeling) yazılmış ve testliydi ama hiçbir üretim kodu onu
çağırmıyordu. Kullanıcı onayıyla (2026-08-19) 4 Grup B modülü birlikte
canlıya alınıyor.

Revision ID: faz288
Revises: faz287
Create Date: 2026-08-19
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz288"
down_revision = "faz287"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "opportunity_quality_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
    )
    op.create_index(
        "ix_opportunity_quality_snapshots_created_at",
        "opportunity_quality_snapshots", ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_opportunity_quality_snapshots_created_at",
        table_name="opportunity_quality_snapshots",
    )
    op.drop_table("opportunity_quality_snapshots")
