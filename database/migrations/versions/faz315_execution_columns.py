"""Faz 315 — Execution Layer, Faz 1 (gerçek testnet emir gönderimi).

Sistem baştan sona saf simülasyondu — bu, o boşluğun ilk, tamamen
opt-in artımı. Yeni sütunların hepsi nullable/additive: mevcut
"simulated" (varsayılan, davranışı değişmeyen) pozisyonlar için hepsi
NULL kalır, sadece execution_mode="testnet" ile açılan yeni pozisyonlar
doldurur.

Revision ID: faz315
Revises: faz313
Create Date: 2026-08-20
"""
import sqlalchemy as sa
from alembic import op

revision = "faz315"
down_revision = "faz313"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("decisions", sa.Column("execution_mode", sa.String(), nullable=True))
    op.add_column("decisions", sa.Column("exchange_order_id", sa.String(), nullable=True))
    op.add_column("decisions", sa.Column("exchange_client_order_id", sa.String(), nullable=True))
    op.add_column("decisions", sa.Column("exchange_stop_order_id", sa.String(), nullable=True))
    op.add_column("decisions", sa.Column("exchange_tp_order_id", sa.String(), nullable=True))
    op.add_column("decisions", sa.Column("exchange_sync_status", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("decisions", "exchange_sync_status")
    op.drop_column("decisions", "exchange_tp_order_id")
    op.drop_column("decisions", "exchange_stop_order_id")
    op.drop_column("decisions", "exchange_client_order_id")
    op.drop_column("decisions", "exchange_order_id")
    op.drop_column("decisions", "execution_mode")
