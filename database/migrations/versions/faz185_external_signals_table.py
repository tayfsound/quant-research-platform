"""Faz 185: external_signals table — TradingView (ve gelecekteki başka)
webhook alarm sinyallerini kalıcı kılar.

TradingView klasik "API key ile veri çek" modeliyle çalışmıyor — Pine Script
alert'leri bir webhook URL'ine HTTP POST gönderiyor (inbound, outbound değil).
Bu tablo o gelen sinyalleri saklıyor; `api/rest/webhooks.py` bunu yazıyor.

Revision ID: faz185
Revises: faz184
Create Date: 2026-08-05
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz185"
down_revision = "faz184"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("time", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("signal", sa.String(16), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id", "time"),
    )
    op.execute("SELECT create_hypertable('external_signals', 'time', if_not_exists => TRUE);")
    op.create_index(
        "ix_external_signals_symbol_time", "external_signals", ["symbol", "time"]
    )


def downgrade() -> None:
    op.drop_index("ix_external_signals_symbol_time", table_name="external_signals")
    op.drop_table("external_signals")
