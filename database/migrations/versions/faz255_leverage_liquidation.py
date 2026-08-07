"""Faz 255: kaldıraç desteği — kullanıcı isteği, "olay kaldıraçta zaten
asıl olay o." Sistem şu ana kadar tamamen spot (1x) çalışıyordu;
simulator/margin.py'de çalışan bir margin hesaplayıcı vardı ama gerçek
pozisyon açma/kapama akışına (decision_recorder.py, position_closer.py)
hiç bağlı değildi.

decisions.leverage: pozisyon açılırken kullanılan gerçek kaldıraç
(varsayılan 1.0 — spot, geriye dönük uyumlu).
decisions.liquidation_price: kaldıraçlı bir pozisyonun gerçekten
iflas edeceği fiyat seviyesi — PositionCloser artık stop/target'tan ÖNCE
bunu kontrol ediyor, kaldıraçlı bir pozisyon gerçekten batarsa sistem
bunu görmezden gelmiyor (fail-fake değil).

Revision ID: faz255
Revises: faz240
Create Date: 2026-08-07
"""
import sqlalchemy as sa
from alembic import op

revision = "faz255"
down_revision = "faz240"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("decisions", sa.Column("leverage", sa.Float(), nullable=False, server_default="1.0"))
    op.add_column("decisions", sa.Column("liquidation_price", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("decisions", "liquidation_price")
    op.drop_column("decisions", "leverage")
