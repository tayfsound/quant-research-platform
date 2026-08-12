"""Faz 247-249: order_book_snapshots'a funding_rate/open_interest.

aggressive_buy_ratio'nun (Faz 214) izlediği AYNI desen — OrderFlowAgent'ın
mikroyapı verisi tek bir tabloda toplanıyor. exchange_gateway/binance/
adapter.py::fetch_funding_rate/fetch_open_interest zaten yazılmıştı ama
yanlış temel URL'e (spot, futures değil) gittiği için hiç çalışmamıştı —
ayrı bir commit'te düzeltildi, burada sadece bu gerçek verinin
saklanacağı sütunlar ekleniyor.

Revision ID: faz249
Revises: faz244
Create Date: 2026-08-12
"""
import sqlalchemy as sa
from alembic import op

revision = "faz249"
down_revision = "faz244"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("order_book_snapshots", sa.Column("funding_rate", sa.Float(), nullable=True))
    op.add_column("order_book_snapshots", sa.Column("open_interest", sa.Float(), nullable=True))
    op.add_column("order_book_snapshots", sa.Column("open_interest_trend", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("order_book_snapshots", "open_interest_trend")
    op.drop_column("order_book_snapshots", "open_interest")
    op.drop_column("order_book_snapshots", "funding_rate")
