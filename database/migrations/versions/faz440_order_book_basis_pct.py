"""Faz 440: order_book_snapshots'a basis_pct (futures premium/iskonto).

faz249_order_book_funding_oi.py'nin (funding_rate/open_interest) İZLEDİĞİ
AYNI desen — exchange_gateway/binance/adapter.py::fetch_premium_index()
(Binance'in /fapi/v1/premiumIndex uç noktası, fetch_funding_rate İLE
AYNI desen) mark price'ın index (spot) price'a göre primini/iskontosunu
hesaplıyor; burada bu gerçek verinin saklanacağı sütun ekleniyor.

Revision ID: faz440
Revises: faz407
Create Date: 2026-09-08
"""
import sqlalchemy as sa
from alembic import op

revision = "faz440"
down_revision = "faz407"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("order_book_snapshots", sa.Column("basis_pct", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("order_book_snapshots", "basis_pct")
