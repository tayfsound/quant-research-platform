"""Faz 299-300 — TP/SL Confluence haftalık anlık görüntüsü.

analytics/tp_sl_confluence.py — "zone of agreement" (S/R + Volume
Profile + Pivot + Donchian + Keltner). Kullanıcı isteği (2026-08-19):
önce ölçüm, sonra "wire edelim" onayıyla RiskTargetStage'e (SADECE
hedef, stop değil) bağlandı.

Revision ID: faz299
Revises: faz296
Create Date: 2026-08-19
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz299"
down_revision = "faz296"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tp_sl_confluence_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
    )
    op.create_index(
        "ix_tp_sl_confluence_snapshots_created_at",
        "tp_sl_confluence_snapshots", ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tp_sl_confluence_snapshots_created_at",
        table_name="tp_sl_confluence_snapshots",
    )
    op.drop_table("tp_sl_confluence_snapshots")
