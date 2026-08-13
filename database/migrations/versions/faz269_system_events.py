"""Faz 269 (Cognitive Core 2.0 / M1): create system_events table.

Veri ve olay altyapısı — sistemdeki önemli olayları (kill switch
tetiklenmesi, ağırlık onayı kararı, rejim değişikliği vb.) TEK, birleşik,
append-only bir tabloda toplamak. Şu ana kadar bu tür olaylar 6 farklı
tabloya (app_settings.updated_by, weight_approvals.status, decisions
vb.) dağılmış, her biri kendi ad-hoc şemasıyla — "sistemde ne oldu, hangi
sırayla" sorusunu cevaplamak için hepsini ayrı ayrı sorgulamak
gerekiyordu. Bu tablo yeni bir "gerçek kaynak" DEĞİL — mevcut tabloların
YERİNE geçmiyor, onları TEKRARLAMADAN üstlerine bir olay zaman çizelgesi
ekliyor (payload'da ilgili tablonun kendi id'sine referans veriliyor).

Gelecekteki feature-lineage/replay/audit işlerinin (Cognitive Core 2.0'ın
geri kalanı) üzerine inşa edeceği temel katman.

Revision ID: faz269
Revises: faz250
Create Date: 2026-08-13
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "faz269"
down_revision = "faz250"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_system_events_created_at", "system_events", ["created_at"])
    op.create_index("ix_system_events_event_type", "system_events", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_system_events_event_type", table_name="system_events")
    op.drop_index("ix_system_events_created_at", table_name="system_events")
    op.drop_table("system_events")
