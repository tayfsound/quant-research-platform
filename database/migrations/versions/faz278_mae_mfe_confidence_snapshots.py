"""Cognitive Core 2.0 — MAE/MFE Bootstrap Güven Aralığı haftalık anlık görüntüsü.

analytics/mae_mfe_scientific.py::bootstrap_quantile_ci() (Faz 469-493)
yazılmış ve testliydi ama hiçbir üretim kodu onu çağırmıyordu — mevcut
nokta tahminlerinin (p90 MAE gibi) GERÇEK belirsizliği hiç raporlanmıyordu.
Collective Intelligence'tan sonraki, council'i etkilemeyen Grup B adayı.

Revision ID: faz278
Revises: faz277
Create Date: 2026-08-18
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz278"
down_revision = "faz277"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mae_mfe_confidence_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_mae_mfe_confidence_snapshots_created_at", "mae_mfe_confidence_snapshots", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_mae_mfe_confidence_snapshots_created_at", table_name="mae_mfe_confidence_snapshots")
    op.drop_table("mae_mfe_confidence_snapshots")
