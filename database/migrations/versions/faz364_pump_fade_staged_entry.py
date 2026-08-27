"""Faz 364 — pump_fade Kademeli Giriş (Staged Entry).

Kullanıcı fikri (2026-08-26), gerçek Binance verisiyle kalibre edildi:
%50 pump tespitinde hedef boyutun sadece %25'i açılır (düşük kaldıraç,
dip'ten stop'a mesafe uzak); fiyat dip-bazlı %80'e ulaşırsa 3 katı
büyüyerek %100'e tamamlanır (bu ikinci bacak yüksek kaldıraç kaldırabilir
— add ile ortak stop arası mesafe çok yakın); ortak stop dip-bazlı %90'da
(gerçek veride 43 sembol/250 günde HİÇ ulaşılmayan bir seviye).

İki bacak iki AYRI `decisions` satırı (iki bağımsız pozisyon, AYNI
stop_loss_price'ı paylaşırlar) — tek satırda iki farklı kaldıracı temsil
etme zorunluluğu yok, mevcut close_due_positions() mekanizması zaten
sembol başına birden fazla açık pozisyonu bağımsız yönetiyor.

Revision ID: faz364
Revises: faz350
Create Date: 2026-08-26
"""
import sqlalchemy as sa
from alembic import op

revision = "faz364"
down_revision = "faz350"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("decisions", sa.Column("staged_entry_add_pending", sa.Boolean(), nullable=True))
    op.add_column("decisions", sa.Column("staged_entry_low_price", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("decisions", "staged_entry_low_price")
    op.drop_column("decisions", "staged_entry_add_pending")
