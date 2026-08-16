"""Faz 268-sonrası: Feature IC haftalık rapor geçmişi.

Kullanıcı isteği — "Feature IC'yi karar hattına bağlama." analytics/
feature_ic.py::compute_feature_ic() zaten gerçek zamanlı çalışıyordu
(GET /feature-ic/) ama hiçbir geçmişi yoktu. Bu tablo periyodik
(haftalık, bkz. services/tasks.py::refresh_feature_ic_report_task)
anlık görüntüleri saklıyor — llm_audit_runs (Faz 271) ile AYNI desen.
Sadece ölçüm/kayıt — hiçbir feature'ı otomatik pasifleştirmiyor.

Revision ID: faz272
Revises: faz271
Create Date: 2026-08-16
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz272"
down_revision = "faz271"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feature_ic_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("features", postgresql.JSONB(), nullable=False),
        sa.Column("total_closed_trades", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_feature_ic_reports_created_at", "feature_ic_reports", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_feature_ic_reports_created_at", table_name="feature_ic_reports")
    op.drop_table("feature_ic_reports")
