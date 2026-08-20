"""Faz 313 — kullanıcı bulgusu (2026-08-20, gerçek KAIAUSDT/PENDLEUSDT/
HUMAUSDT/NOMUSDT/RPLUSDT örnekleri): "son dört başa baş çekilmiş görünen
pozisyon zarar ile kapanmış." Kök neden: services/position_closer.py'nin
breakeven_stop sınıflandırması SADECE stop fiyatının o anki (ratchet
sonrası) KONUMUNA bakıyordu, kaybın orijinal (ratchet öncesi) stop
mesafesine göre GERÇEKTEN küçültülüp küçültülmediğini hiç doğrulamıyordu
— stop_loss_price sütunu ratchet'te YERİNDE ÜZERİNE YAZILIYORDU, orijinal
değer kalıcı olarak kayboluyordu.

Bu migration decisions.original_stop_loss_price'ı ekliyor — pozisyon
AÇILIŞINDA bir kez yazılır, breakeven/trailing ratchet ASLA bu sütunu
değiştirmez (sadece stop_loss_price'ı günceller). Mevcut açık pozisyonlar
için NULL kalır (fail-closed — services/position_closer.py NULL'ı "orijinal
mesafe doğrulanamıyor" olarak ele alır).

Revision ID: faz313
Revises: faz299
Create Date: 2026-08-20
"""
import sqlalchemy as sa
from alembic import op

revision = "faz313"
down_revision = "faz299"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("decisions", sa.Column("original_stop_loss_price", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("decisions", "original_stop_loss_price")
