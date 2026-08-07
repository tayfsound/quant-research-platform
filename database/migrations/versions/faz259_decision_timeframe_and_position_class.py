"""Faz 259: kullanıcı isteği — orta-vadeli pozisyon katmanı (günlük/4h
analiz, ayrı sermaye havuzu, "sakin ama harekete geçince büyük oynayan"
bir yapı). Bunu kısa-vadeli katmandan gerçekten ayrı tutabilmek (aynı
sermaye/concurrent-position sayacını paylaşmamaları) için, decisions
tablosunda hangi zaman diliminden geldiğini SORGULANABİLİR şekilde
bilmemiz gerekiyor — önceden bu bilgi sadece agent_contributions
içindeki JSON'da (market_snapshot.timeframe) gömülüydü, SQL ile
filtrelenemiyordu.

Revision ID: faz259
Revises: faz255
Create Date: 2026-08-07
"""
import sqlalchemy as sa
from alembic import op

revision = "faz259"
down_revision = "faz255"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("decisions", sa.Column("timeframe", sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column("decisions", "timeframe")
