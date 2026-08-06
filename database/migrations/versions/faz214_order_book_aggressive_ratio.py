"""Faz 214: order_book_snapshots'a aggressive_buy_ratio.

Gerçek bulgu: OrderFlowAgent'ın aggressive_buy_ratio girdisi her zaman
sabit 0.5'e (tam nötr) düşüyordu — hiçbir gerçek veri kaynağı yoktu.
Binance'in genel/kimliksiz erişilebilen son-işlemler (recent trades)
uç noktası isBuyerMaker alanıyla bunu gerçekten hesaplamayı mümkün
kılıyor — order book derinliğinden ayrı, gerçek taker akışı.

Revision ID: faz214
Revises: faz196
Create Date: 2026-08-06
"""
import sqlalchemy as sa
from alembic import op

revision = "faz214"
down_revision = "faz196"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "order_book_snapshots",
        sa.Column("aggressive_buy_ratio", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("order_book_snapshots", "aggressive_buy_ratio")
