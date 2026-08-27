"""Faz 365: liquidation_events — Binance Futures'ın gerçek, ücretsiz
zorunlu-kapanış (forceOrder) akışının ham zaman serisi. Backlog #49
("MempoolAgent") — kullanıcı kararı: önce veri toplama/ölçüm, ajan
oylamasına bağlama ayrı bir tur.

Revision ID: faz365
Revises: faz364
Create Date: 2026-08-26
"""
import sqlalchemy as sa
from alembic import op

revision = "faz365"
down_revision = "faz364"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "liquidation_events",
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        # "LONG" = zorunlu SATIŞ (LONG pozisyon likide edildi), "SHORT" =
        # zorunlu ALIŞ (SHORT pozisyon likide edildi) — Binance'in ham
        # SELL/BUY alanı, likide olan pozisyonun YÖNÜNE çevrilerek saklanıyor
        # (okunurluk için, ham veriden kayıpsız türetilebilir).
        sa.Column("liquidated_side", sa.String(8), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("notional_usd", sa.Float(), nullable=False),
    )
    op.execute("SELECT create_hypertable('liquidation_events', 'time', if_not_exists => TRUE);")
    op.create_index("ix_liquidation_events_symbol_time", "liquidation_events", ["symbol", "time"])


def downgrade() -> None:
    op.drop_index("ix_liquidation_events_symbol_time", table_name="liquidation_events")
    op.drop_table("liquidation_events")
