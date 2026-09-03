"""Faz 407 — kullanıcı isteği: "ölçtüğümüz her veri için zaman içindeki
stabilitesini de ölçelim." Korelasyon (risk/cross_symbol_correlation.py)
şu ana kadar HİÇ kaydedilmiyordu — her cognitive cycle'da anlık
hesaplanıp atılıyordu, "bu korelasyon istikrarlı mı yoksa gürültülü mü"
sorusu asla cevaplanamıyordu (gerçek kanıt: BTC-ETH std=0.042 vs
NVDA-AMD std=0.181, aynı >0.7 okumayı üretebiliyor ama biri güvenilir
biri gürültü). market_state_snapshots ile AYNI desende (id/created_at/
result JSONB) periyodik bir anlık görüntü saklıyor — services/market_
state_gatherer.py'nin ZATEN her 5 dakikada çektiği watchlist getirilerini
yeniden kullanıyor, ek bir API çağrısı yok.

Revision ID: faz407
Revises: faz401
Create Date: 2026-09-03
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz407"
down_revision = "faz401"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "correlation_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_correlation_snapshots_created_at", "correlation_snapshots", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_correlation_snapshots_created_at", table_name="correlation_snapshots")
    op.drop_table("correlation_snapshots")
