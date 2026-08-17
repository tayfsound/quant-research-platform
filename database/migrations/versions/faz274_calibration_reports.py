"""Cognitive Core 2.0 / M4 — Probability Calibration (ECE) haftalık rapor geçmişi.

Kullanıcı isteği: council'i hiç etkilemeyen, ölçüm-only Cognitive Core
modüllerini birer birer canlıya (izlenebilir hale) alalım. ECE ilk aday —
analytics/calibration_uncertainty.py zaten gerçek zamanlı çalışıyordu
(GET /calibration/) ama hiçbir geçmişi yoktu. Bu tablo periyodik (haftalık)
anlık görüntüleri saklıyor — feature_ic_reports/llm_audit_runs ile AYNI desen.

Revision ID: faz274
Revises: faz273
Create Date: 2026-08-17
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz274"
down_revision = "faz273"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calibration_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("total_closed_trades", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_calibration_reports_created_at", "calibration_reports", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_calibration_reports_created_at", table_name="calibration_reports")
    op.drop_table("calibration_reports")
