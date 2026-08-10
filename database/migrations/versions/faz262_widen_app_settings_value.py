"""Faz 262: kritik bulgu — app_settings.value VARCHAR(256) idi.
symbol_leverage (izlenen her sembol için JSON dict) watchlist büyüdükçe
bu sınırı gerçekten aşabiliyor — üretimde 15 sembolle zaten 175/256
karaktere ulaşmıştı, testlerde ise paylaşılan test DB'sinde birikip
StringDataRightTruncation ile tam iki testi çökertti (test_pairs_trader.py,
test_position_lifecycle.py). TEXT'e genişletmek veri kaybı riski taşımıyor
(Postgres'te VARCHAR->TEXT dönüşümü satır içi, anında).

Revision ID: faz262
Revises: faz259
Create Date: 2026-08-10
"""
import sqlalchemy as sa
from alembic import op

revision = "faz262"
down_revision = "faz259"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("app_settings", "value", type_=sa.Text(), existing_nullable=False)


def downgrade() -> None:
    op.alter_column("app_settings", "value", type_=sa.String(256), existing_nullable=False)
