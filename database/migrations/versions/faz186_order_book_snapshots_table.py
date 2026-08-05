"""Faz 186: order_book_snapshots table — Order Flow ajanının verisi.

Bilinçli tasarım kararı (saklama maliyeti tartışmasından): ham order book'un
tamamını (yüzlerce bid/ask seviyesi, saniyede defalarca değişen) saklamak
yerine, sadece Order Flow ajanının gerçekten ihtiyaç duyduğu türetilmiş
metrikleri saklıyoruz — best_bid/best_ask/toplam hacim/dengesizlik/spread.
Bu, hem depolama maliyetini hem karmaşıklığı bir kerede ortadan kaldırıyor.

Revision ID: faz186
Revises: faz185
Create Date: 2026-08-05
"""
import sqlalchemy as sa
from alembic import op

revision = "faz186"
down_revision = "faz185"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_book_snapshots",
        sa.Column("exchange", sa.String(32), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("time", sa.DateTime(), nullable=False),
        sa.Column("best_bid", sa.Float(), nullable=False),
        sa.Column("best_ask", sa.Float(), nullable=False),
        sa.Column("bid_volume", sa.Float(), nullable=False),
        sa.Column("ask_volume", sa.Float(), nullable=False),
        sa.Column("imbalance", sa.Float(), nullable=False),
        sa.Column("spread_bps", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("exchange", "symbol", "time"),
    )
    op.execute("SELECT create_hypertable('order_book_snapshots', 'time', if_not_exists => TRUE);")


def downgrade() -> None:
    op.drop_table("order_book_snapshots")
