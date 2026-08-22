"""Faz 350 — Pozisyon Havuzu / Max Confidence Modu.

Kullanıcı fikri: council'dan çıkan yönlü (LONG/SHORT, risk-onaylı) kararlar
hemen açılmak yerine bir pencere boyunca (varsayılan 15dk) havuzda
biriktirilir; pencere kapanınca sadece en yüksek confidence'lı top-K aday
GERÇEK, TAZE fiyattan açılır, geri kalanı "rejected" olarak işaretlenir.

`decisions` tablosunu YENİDEN KULLANMAK yerine ayrı bir tablo: mevcut
status-tabanlı sorguların (dashboard/analytics, ~30+ yer) "pooled" gibi
yeni bir status değeriyle kirlenmesi riskini baştan eler. Bir aday
seçilirse GERÇEK açılış normal DecisionPersistor akışıyla `decisions`'a
kaydedilir (bkz. services/position_pool.py) — bu tablo sadece havuzun
kendi yaşam döngüsünü tutar.

Revision ID: faz350
Revises: faz331
Create Date: 2026-08-22
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz350"
down_revision = "faz331"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "position_pool_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("entry_price_at_pool", sa.Float(), nullable=False),
        sa.Column("stop_loss_distance", sa.Float(), nullable=False),
        sa.Column("take_profit_distance", sa.Float(), nullable=False),
        sa.Column("planned_notional_usd", sa.Float(), nullable=False),
        sa.Column("leverage", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("weight_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("belief_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("pooled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_closes_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resulting_decision_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_position_pool_candidates_status_window",
        "position_pool_candidates",
        ["status", "window_closes_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_position_pool_candidates_status_window",
        table_name="position_pool_candidates",
    )
    op.drop_table("position_pool_candidates")
