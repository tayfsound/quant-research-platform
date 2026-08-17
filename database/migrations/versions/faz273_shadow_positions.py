"""Faz 268-sonrası: Shadow Mode (Macro-Only karşılaştırma).

Kullanıcı bulgusu — 23 pozisyonluk örneklemde macro ajanının yönlü
tahminleri %86 isabetli görünüyordu, diğer 8 ajanın "gürültü ekleyip
eklemediği" sorusu doğdu. Kullanıcıyla üzerinde anlaşılan çerçeve
(3 seçenekten A): council'in kararlarını hiç etkilemeyen, SADECE
macro'nun kendi yönüne göre sanal (paper) pozisyon açıp kapatan izole
bir gölge takipçi — pump_fade_strategy.py ile AYNI izolasyon felsefesi
(services/macro_shadow_tracker.py). Bu tablo `decisions`'tan KASITLI
olarak AYRI: shadow pozisyonlar gerçek sermaye değil, gerçek dashboard
PnL/ROI sayılarına asla karışmamalı — aynı tabloyu paylaşıp her okuma
noktasında filtre unutma riskini almak yerine yapısal olarak izole.

Revision ID: faz273
Revises: faz272
Create Date: 2026-08-17
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz273"
down_revision = "faz272"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shadow_positions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("direction", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("exit_price", sa.Float(), nullable=True),
        sa.Column("stop_loss_price", sa.Float(), nullable=False),
        sa.Column("take_profit_price", sa.Float(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
        sa.Column("pnl_pct", sa.Float(), nullable=True),
        sa.Column("exit_reason", sa.String(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_shadow_positions_source_symbol_status", "shadow_positions", ["source", "symbol", "status"])


def downgrade() -> None:
    op.drop_index("ix_shadow_positions_source_symbol_status", table_name="shadow_positions")
    op.drop_table("shadow_positions")
