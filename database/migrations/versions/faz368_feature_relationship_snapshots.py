"""Faz 368: Feature Relationship (redundancy matrix + koşullu IC) haftalık
rapor geçmişi.

Kullanıcı isteği: Feature IC'deki negatif IC'li feature'ların (trend, EMA,
momentum, VWAP) aslında aynı latent bilginin tekrarı olduğu şüphesi —
gerçek veriyle doğrulandı (bkz. analytics/feature_relationship.py). Bu
tablo periyodik (haftalık, services/tasks.py::refresh_feature_
relationship_report_task) anlık görüntüleri saklıyor — feature_ic_reports
(Faz 268-sonrası) ile AYNI desen. Sadece ölçüm/kayıt — karar hattına
bağlanmıyor.

Revision ID: faz368
Revises: faz367
Create Date: 2026-08-28
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz368"
down_revision = "faz367"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feature_relationship_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redundancy", postgresql.JSONB(), nullable=False),
        sa.Column("conditional_ic", postgresql.JSONB(), nullable=False),
        sa.Column("total_closed_trades", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_feature_relationship_reports_created_at", "feature_relationship_reports", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_feature_relationship_reports_created_at", table_name="feature_relationship_reports")
    op.drop_table("feature_relationship_reports")
