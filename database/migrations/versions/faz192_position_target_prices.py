"""Faz 192: decisions'a gerçek stop-loss/take-profit fiyat seviyeleri.

Faz 191'de RiskTargetStage gerçek ATR'den take_profit/stop_loss (RİSK
MAGNİTÜDÜ, mutlak fiyat değil) kurmaya başladı. Bir pozisyon gerçekten
açıldığında bu magnitüd, entry_price'a göre mutlak bir fiyat seviyesine
çevrilip burada saklanıyor — services/position_closer.py artık sadece
vadeye (hold_seconds) göre değil, gerçek fiyat bu seviyelere ulaştığında
da pozisyonu kapatabiliyor.

Revision ID: faz192
Revises: faz189
Create Date: 2026-08-05
"""
import sqlalchemy as sa
from alembic import op

revision = "faz192"
down_revision = "faz189"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("decisions", sa.Column("stop_loss_price", sa.Float(), nullable=True))
    op.add_column("decisions", sa.Column("take_profit_price", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("decisions", "take_profit_price")
    op.drop_column("decisions", "stop_loss_price")
