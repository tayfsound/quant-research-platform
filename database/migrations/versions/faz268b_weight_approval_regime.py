"""Faz 268b: weight_approvals.regime kolonu — Regime-Aware Learning
(yol haritası Faz B). NULL = global (rejimden bağımsız) öneri, mevcut
tüm satırlar geriye dönük NULL kalır (davranış değişmiyor).

Revision ID: faz268b
Revises: faz262
Create Date: 2026-08-11
"""
import sqlalchemy as sa
from alembic import op

revision = "faz268b"
down_revision = "faz262"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("weight_approvals", sa.Column("regime", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("weight_approvals", "regime")
