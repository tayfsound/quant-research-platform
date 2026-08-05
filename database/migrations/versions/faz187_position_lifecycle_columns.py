"""Faz 187: decisions'a gerçek pozisyon yaşam döngüsü kolonları.

Gerçek bulgu: `decisions.status` neredeyse hiç 'pending' dışına çıkmıyordu
çünkü canlı üretim yolunda (CognitiveOrchestrator.run_cycle) pnl, ForwardOutcome
ile aynı anda zaten elde var olan 100 barlık geçmiş pencere üzerinden ANINDA
hesaplanıp ctx.outcome'a "sanki işlem zaten kapanmış gibi" yazılıyordu — ama
DB'ye status='pending' olarak düşüyordu ve hiçbir şey onu 'completed'e
çevirmiyordu. Yani ne gerçek bir "açık pozisyon" kavramı vardı (entry_price/
opened_at yok) ne de gerçek bir kapanış (gerçek zaman geçmesi beklenmiyordu).

Bu migration + services/position_closer.py: pozisyon gerçekten opened_at'te
açılıyor, gerçek zaman geçtikten sonra gerçek güncel fiyatla kapanıyor.

Revision ID: faz187
Revises: faz186
Create Date: 2026-08-05
"""
import sqlalchemy as sa
from alembic import op

revision = "faz187"
down_revision = "faz186"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("decisions", sa.Column("entry_price", sa.Float(), nullable=True))
    op.add_column("decisions", sa.Column("exit_price", sa.Float(), nullable=True))
    op.add_column("decisions", sa.Column("quantity", sa.Float(), nullable=True))
    op.add_column("decisions", sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("decisions", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("decisions", "closed_at")
    op.drop_column("decisions", "opened_at")
    op.drop_column("decisions", "quantity")
    op.drop_column("decisions", "exit_price")
    op.drop_column("decisions", "entry_price")
